import maslite
import queue
import multiprocessing
from multiprocessing.context import BaseContext
from itertools import count
from time import monotonic, sleep, process_time
import platform
default_context = "spawn" if platform.system() != 'Linux' else "fork"

class Stop:
    """ a simple stop signal."""

class Link:
    """ scaffolding to keep queues and subprocess together """
    def __init__(self,name, ctx, speed) -> None:
        self.to_main = ctx.Queue()
        self.to_sub_proc = ctx.Queue()
        self.sub_proc = SubProc(ctx=ctx, mq_to_main=self.to_main, mq_to_self=self.to_sub_proc, name=name, speed=speed)
    def start(self):
        self.sub_proc.start()
    def is_alive(self):
        return self.sub_proc.is_alive()
    @property
    def exitcode(self):
        return self.sub_proc.exitcode


class LogisticUnit:
    """ A standard message 
    This representation of a LU is used to handle transfers.
    """
    ids = count(start=1)
    def __init__(self, route) -> None:
        self.id = next(LogisticUnit.ids)
        assert isinstance(route, list)
        self.route = route
        self.length = 500 #mm
    def next_agent(self, current_agent):
        ix = self.route.index(current_agent)
        if ix == len(self.route):
            return None
        else:
            return self.route[ix+1]

    def __str__(self) -> str:
        return f"LogisticUnit:({self.id}): Route: {self.route}"

class TransferNotification(maslite.AgentMessage):
    def __init__(self, s, r):
        super().__init__(sender=s,receiver=r)

class TransferAcceptance(maslite.AgentMessage):
    def __init__(self, s, r):
        super().__init__(sender=s,receiver=r)

class Transfer(maslite.AgentMessage):
    def __init__(self, s, r, obj):
        super().__init__(sender=s,receiver=r)
        self.obj = obj

class TimeSignal:
    def __init__(self, timestamp):
        self.timestamp = timestamp


class Conveyor(maslite.Agent):
    def __init__(self, id) -> None:
        super().__init__(id)
        ops = {
            TransferNotification.__name__: self.tn,
            TransferAcceptance.__name__: self.ta,
            Transfer.__name__: self.transfer
        }
        self.operations.update(ops)
        self.speed = 1000  # mm/s
        self.length = 2000  # mm
        self.lu = None

    def update(self):
        for msg in self.inbox:
            ops = self.operations.get(msg.topic)
            ops(msg)
        self.inbox.clear()
    
    def tn(self, msg):
        assert isinstance(msg, TransferNotification)
        # all conveyors are operating at the same speed, so I spare the math.
        self.send(TransferAcceptance(self.uuid, r=msg.s))
    
    def ta(self,msg):
        assert isinstance(msg, TransferAcceptance)
        self.send(Transfer(self.uuid, r=msg.s, obj=self.lu))
    
    def transfer(self, msg):
        assert isinstance(msg, Transfer)
        lu = msg.obj
        self.put(lu,leading_edge=0)

    def put(self, lu, leading_edge):
        assert isinstance(lu, LogisticUnit)
        self.lu = lu
        
        zzz = (self.length - leading_edge) / self.speed

        next_agent_on_route = lu.next_agent(self.uuid)
        if next_agent_on_route is None:
            print(f"LU arrived: {lu}") 
        else:    
            tn = TransferNotification(s=self, r=next_agent_on_route)
            self.set_alarm(zzz, tn)


class AcceleratedClock(maslite.Clock):
    """ A clock that is synchronized across all processes"""
    def __init__(self, scheduler_api, speed=1.0):
        super().__init__(scheduler_api)
        assert isinstance(speed,float)
        self.speed = speed
        self._time = 0.0

    def tick(self, limit=None):
        pass


class Scheduler(maslite.Scheduler):
    def __init__(self, logger=None, mq_to_main=None, speed=1.0):
        super().__init__(logger, real_time=False)
        self.clock = AcceleratedClock(scheduler_api=self, speed=speed)
        self.mq_to_main = mq_to_main

    def process_mail_queue(self):  # -- OVERRIDE
        # return super().process_mail_queue()
        for msg in self.mail_queue:
            print(msg)
            assert isinstance(msg, maslite.AgentMessage)
            recipients = self.mailing_lists.get_mail_recipients(message=msg)
            if recipients:  # it's a local message
                self.send_to_recipients(msg=msg, recipients=recipients)
            else:  # it's an inter proc message
                self.mq_to_main.to_main.put(msg)
        self.mail_queue.clear()


class SubProc:  # Partition of the the simulation.
    def __init__(self, ctx:BaseContext, 
                 mq_to_main:multiprocessing.Queue,
                 mq_to_self:multiprocessing.Queue,
                 speed: float, 
                 name: str) -> None:
        self.ctx = ctx
        self.exit = ctx.Event()
        self.mq_to_main = mq_to_main
        self.mq_to_self = mq_to_self
        self.scheduler = Scheduler(speed=speed, mq_to_main=mq_to_main)
        self.process = ctx.Process(group=None, target=self.run, name=name, daemon=False)
        self.name = name
        self._quit: bool = False

    def start(self):
        print("starting")
        self.process.start()

    def is_alive(self):
        return self.process.is_alive()

    @property
    def exitcode(self):
        return self.process.exitcode

    def add(self, agent):
        print(f"adding agent {agent.uuid}")
        self.scheduler.add(agent)

    def process_inter_proc_mail(self):
        while not self._quit:
            try:
                msg = self.mq_to_self.get_nowait()
                if isinstance(msg, TimeSignal):
                    # the schedulers clock is updated with the 
                    # global time from the main process.
                    self.scheduler.clock._time = msg.timestamp

                elif isinstance(msg, maslite.AgentMessage):
                    self.scheduler.mail_queue.append(msg)

                elif isinstance(msg, Stop):
                    print(f"{self.name} received stop signal")
                    self._quit = True
                    self.exit.set()
                    break

                else:
                    raise Exception(f"{msg}")
            except queue.Empty:
                return
        
    def run(self):
        while not self._quit:
            self.process_inter_proc_mail()
            self.scheduler.run()


class MPmain:
    """ The main process for inter-process message exchange """
    def __init__(self, speed=1.0, context=default_context) -> None:
        self._ctx = multiprocessing.get_context(context)
        
        self.schedulers = {}
        self.agents = {}  # agent.id: proc.id
        self._quit = False

        # time keeping variables.
        self.speed = speed
        self._start_time = -1
        self._time = 0.0

    @property
    def time(self):
        now = monotonic()
        if self._start_time == -1:
            self._start_time = now
        self._time = (now-self._start_time) * self.speed
        return self._time

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):  # signature requires these, though I don't use them.
        self._stop()

    def new_partition(self):
        name = str(len(self.schedulers)+1)
        link = Link(name, ctx=self._ctx,speed=self.speed)  # communication link between mpmain and a scheduler.
        self.schedulers[name] = link
        return link.sub_proc
    
    def _start(self):
        procs = []
        for name, link in self.schedulers.items():
            assert isinstance(link, Link)

            for id in link.sub_proc.scheduler.agents.keys():
                self.agents[id] = name 

            link.start()
            print(f"{name} starting")
            procs.append(link)

        while not all(p.is_alive() is True for p in procs):
            sleep(0.01)  # wait for the OS to launch the procs.
        print(f"all {len(self.schedulers)} started")

    def _stop(self):
        procs = []
        for link in self.schedulers.values():
            assert isinstance(link,Link)

            link.to_sub_proc.put(Stop())  # send stop signal.
            procs.append(link)
            print(f"{link.sub_proc.name} stopping")
        while any(p.is_alive() for p in procs):
            sleep(0.01)  # wait until all subprocesses have stopped.

        # multiprocessing can't shut down until all message queues are 
        # empty, so we need to purge the system.
        for link in self.schedulers.values():
            assert isinstance(link, Link)
            while not link.to_main.empty:
                _ = link.to_main.get_nowait()
            while not link.to_sub_proc.empty:
                _ = link.to_sub_proc.get_nowait()
        print(f"all {len(self.schedulers)} schedulers stopped")

    def run(self, timeout=8):
        self._start()
        try:
            while not self._quit:
                if process_time() > timeout:
                    return
                self.process_mail_queue()
        except KeyboardInterrupt:
            pass

    def process_mail_queue(self):
        now = self.time # record the time.
        for name, link in self.schedulers.items():
            
            assert isinstance(link, Link)
            # main sends the time to all sub procs.
            link.to_sub_proc.put(TimeSignal(now))

            for _ in range(link.to_main.qsize()):
                try:
                    msg = link.to_main.get_nowait()
                    print(msg)
                    if isinstance(msg, Stop):
                        self._quit = True
                        print("main received Stop")

                    elif isinstance(msg, maslite.AgentMessage):
                        link_name = self.agents[msg.r]
                        _link = self.schedulers[link_name]
                        assert isinstance(_link,Link)
                        _link.to_sub_proc.put(msg)

                    else:
                        raise Exception(f"unhandled message type: {msg}")
                    
                except queue.Empty:
                    if link.is_alive():
                        break  # break and move to next link.
                    elif link.exitcode == -9:
                        raise ChildProcessError(f"{name}:Out of memory")
                    elif link.exitcode != 0:
                        raise ChildProcessError(f"{name}: {link.exitcode}")
                    else:
                        raise Exception


def test_multiprocessing():
    """
    Demonstrates the multiprocessing where mpmain has two schedulers
    which each have two agents (4 agents in total).
    Each agent decides at random who to send a message to. 
    The demonstration stops when all messages have been signed by all agents.
    """
    with MPmain(speed=100.0) as main:
    
        a1 = Conveyor(1)
        a2 = Conveyor(2)
        a3 = Conveyor(3)
        a4 = Conveyor(4)

        lu = LogisticUnit(route=[1,2,3,4])
        leading_edge = (a1.length / 2) + (lu.length / 2)

        s1 = main.new_partition()
        s1.add(a1)
        s1.add(a2)

        s2 = main.new_partition()
        s2.add(a3)
        s2.add(a4)

        a1.put(lu, leading_edge)

        main.run()

if __name__ == "__main__":
    test_multiprocessing()
    # output:
    # -------------------------------
    # Registering agent Conveyor 1
    # adding agent 2
    # Registering agent Conveyor 2
    # adding agent 3
    # Registering agent Conveyor 3
    # adding agent 4
    # Registering agent Conveyor 4
    # starting
    # 1 starting
    # starting
    # 2 starting
    # all 2 started
    #
    # agents messages
    #
    # 1 stopping
    # 2 stopping
    # 2 received stop signal
    # 1 received stop signal
    # all 2 schedulers stopped