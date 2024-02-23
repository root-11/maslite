from math import inf
import maslite
import queue
import multiprocessing
from multiprocessing.context import BaseContext
from itertools import count
from time import monotonic, sleep, process_time
import platform
default_context = "spawn" if platform.system() != 'Linux' else "fork"

class Stop:
    ids = count(start=1)
    """ a simple stop signal."""
    def __init__(self) -> None:
        self.id = next(self.ids)

class Link:
    """ scaffolding to keep queues and subprocess together """
    def __init__(self,name, ctx, global_time) -> None:
        self.to_main = ctx.Queue()
        self.to_sub_proc = ctx.Queue()
        self.sub_proc = SubProc(ctx=ctx, mq_to_main=self.to_main, mq_to_self=self.to_sub_proc, global_time=global_time, name=name)
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
        super().__init__(sender=s,receiver=r, direct=True)

class TransferAcceptance(maslite.AgentMessage):
    def __init__(self, s, r):
        super().__init__(sender=s,receiver=r, direct=True)

class Transfer(maslite.AgentMessage):
    def __init__(self, s, r, obj):
        super().__init__(sender=s,receiver=r, direct=True)
        self.obj = obj

class TimeSignal:
    def __init__(self, timestamp, confirmation=None):
        self.timestamp = timestamp
        self.confirmation = confirmation
    def __str__(self) -> str:
        if not self.confirmation:
            return f"Setting time: {self.timestamp}"
        return f"Time set at {self.confirmation}: {self.timestamp}"


class Conveyor(maslite.Agent):
    def __init__(self, id) -> None:
        super().__init__(id)
        ops = {
            TransferNotification.__name__: self.transfer_notification,
            TransferAcceptance.__name__: self.transfer_acceptance,
            Transfer.__name__: self.transfer
        }
        self.operations.update(ops)
        self.speed = 1000  # mm/s
        self.length = 2000  # mm
        self.lu = None

    def update(self):
        assert isinstance(self._clock, RemoteControlledClock)
        for msg in self.inbox:
            print(f"Time: {self.time}: Message: {msg}")
            ops = self.operations.get(msg.topic)
            ops(msg)
        self.inbox.clear()
    
    def transfer_notification(self, msg):
        assert isinstance(msg, TransferNotification)
        # all conveyors are operating at the same speed, so I spare the math.
        self.send(TransferAcceptance(self.uuid, r=msg.sender))
    
    def transfer_acceptance(self,msg):
        assert isinstance(msg, TransferAcceptance)
        self.send(Transfer(s=self.uuid, r=msg.sender, obj=self.lu))
        self.lu = None
    
    def transfer(self, msg):
        assert isinstance(msg, Transfer)
        lu = msg.obj
        self.put(lu,leading_edge=0)

    def put(self, lu, leading_edge):
        print(f"{self.uuid}: LU received")
        assert isinstance(lu, LogisticUnit)
        self.lu = lu
        
        zzz = (self.length - leading_edge) / self.speed

        next_agent_on_route = lu.next_agent(self.uuid)
        if next_agent_on_route is None:
            print(f"{self.uuid}: LU arrived at destination: {lu}") 
        else:
            print(f"{self.uuid}: set to transfer LU in {zzz} seconds")
            tn = TransferNotification(s=self, r=next_agent_on_route)
            self.set_alarm(zzz, tn)


class RemoteControlledClock(maslite.Clock):
    """ 
    A clock that is synchronized across all processes
    by being remote controlled by MPmain
    """
    def __init__(self, scheduler_api, global_time):
        super().__init__(scheduler_api)
        scheduler_api.clock = self
        self._time = 0.0
        self.global_time = global_time

    def tick(self, limit=None):
        # local time only updates at `tick` to prevent that 
        # individual agents experience different timestamps 
        # during the same update cycle.
        self._time = self.global_time.value


# Here I'm overriding the default maslite.Scheduler to 
# 1. Add the remote controlled clock, 
# 2. Add the message queue to return messages to MPmain
# 3. Patch the method process mail queue, so that messages
#    to agents not governed by the local scheduler are sent
#    to MPmain for redistribution. 

class Scheduler(maslite.Scheduler):
    def __init__(self, logger=None, mq_to_main=None, mq_to_self=None):
        super().__init__(logger)
        self.mq_to_main = mq_to_main
        self.mq_to_self = mq_to_self
        self.clock = None  # we need to set the remote controlled clock!

    def process_mail_queue(self):  # -- OVERRIDE
        self.process_inter_proc_mail()

        for msg in self.mail_queue:
            print(msg)
            assert isinstance(msg, maslite.AgentMessage)
            
            if msg.direct:
                if msg.receiver in self.agents:
                    self.send_to_recipients(msg=msg, recipients=[msg.receiver])
                else:  # it's an inter proc message
                    self.mq_to_main.put(msg)
            else:
                recipients = self.mailing_lists.get_mail_recipients(message=msg)
                locals = [r for r in recipients if r in self.agents]
                if locals:
                    self.send_to_recipients(msg=msg, recipients=locals)
                else:
                    pass  # global subscription is not allowed.                    
            
        self.mail_queue.clear()
    
    def process_inter_proc_mail(self):
        while not self._quit:
            try:
                msg = self.mq_to_self.get_nowait()

                if isinstance(msg, maslite.AgentMessage):
                    self.scheduler.mail_queue.append(msg)

                elif isinstance(msg, Stop):
                    print(f"received stop signal {msg.id}")
                    self._quit = True
                    break

                else:
                    raise Exception(f"{msg}")
            except queue.Empty:
                return


class SubProc:  # Partition of the the simulation.
    def __init__(self, ctx:BaseContext, 
                 mq_to_main:multiprocessing.Queue,
                 mq_to_self:multiprocessing.Queue,
                 global_time,
                 name: str) -> None:
        self.ctx = ctx
        self.exit = ctx.Event()
        self.mq_to_main = mq_to_main
        self.mq_to_self = mq_to_self
        self.scheduler = Scheduler(mq_to_main=mq_to_main, mq_to_self=mq_to_self)
        self.clock = RemoteControlledClock(self.scheduler, global_time=global_time)
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
        
    def run(self):
        self.scheduler.clock.set_alarm(10_000, Transfer(1,2,3), False)
        self.scheduler.run()
        # when the scheduler is done running, we
        # need to stop the sub process:
        self.exit.set()


class SimClock:  # MPmains clock for all partitions.
    def __init__(self,speed) -> None:
        if not speed > 0:
            raise ValueError("negative speed? {speed}")
        self.start_time = -1
        self.speed = speed 
        self.wall_time = 0.0
    @property
    def now(self):
        now = self.wall_time = monotonic()
        if self.start_time == -1:
            self.start_time = now
        # return self.start_time + (now-self.start_time)*self.speed
        return (now-self.start_time)*self.speed
    def __str__(self) -> str:
        return f"Wall: {self.wall_time}: Sim:{self.now}"
    def __repr__(self) -> str:
        return self.__str__()
    
class MPmain:
    """ The main process for inter-process message exchange """
    def __init__(self, speed=1.0, context=default_context) -> None:
        self._ctx = multiprocessing.get_context(context)
        
        self.schedulers = {}
        self.agents = {}  # agent.id: proc.id
        self._quit = False

        # time keeping variables.
        self.clock = SimClock(speed=speed)
        self.global_time = self._ctx.Value('d', 0.0)  # shared multi proc value.

    @property
    def time(self):
        return self.clock.now

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):  # signature requires these, though I don't use them.
        self._stop()

    def new_partition(self):
        name = str(len(self.schedulers)+1)
        link = Link(name, ctx=self._ctx, global_time=self.global_time)  # communication link between mpmain and a scheduler.
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

    def run(self, timeout=10):
        self._start()
        try:
            while not self._quit:
                if process_time() > timeout:
                    return
                self.global_time.value = self.clock.now  # update time for all subprocs
                self.process_inter_proc_mail()

        except KeyboardInterrupt:
            pass

    def process_inter_proc_mail(self):
        for name, link in self.schedulers.items():
            assert isinstance(link, Link)

            for _ in range(link.to_main.qsize()):
                try:
                    msg = link.to_main.get_nowait()
                    if isinstance(msg, Stop):
                        self._quit = True
                        print("main received Stop")

                    elif isinstance(msg, maslite.AgentMessage):
                        if not msg.direct:
                            raise ValueError("Inter proc subscription is not allowed.")
                        link_name = self.agents[msg.receiver]
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
    Demonstrates multiprocessing where 4 conveyors
    handing over a box from one processor to another,
    illustrating that the 2 simulations can be fully 
    synchronised using nothing but a shared clock.
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

        main.run(timeout=50)
        print("!")

def test_time_resolution():
    """ test proves that time progresses correctly. """
    sim_clock, wall_clock = [],[]
    clock_speed = 10_000

    sc = SimClock(clock_speed)
    # after setting clock speed, we now run the clock for 100 steps.
    for _ in range(100):
        sim_now = sc.now
        wall_now = sc.wall_time

        wall_clock.append(wall_now)
        sim_clock.append(sim_now)
        # the sim time and wall clock time has now been recorded.
    
    # now we walk through each pair of values in the list of 
    # sim_clock and wall_clock and measure the step size.
    # by dividing the sim_step with wall_step, we should get the
    # original clock speed back.
    dtx = []
    for ix in range(len(sim_clock)-1):
        sim_step = sim_clock[ix+1] - sim_clock[ix]
        wall_step = wall_clock[ix+1] - wall_clock[ix]
        dtx.append(sim_step / wall_step)
    assert set(dtx) == {clock_speed}
    # The assertion above guarantees two things:
    # 1. That the sim clock steps are of same size.
    # 2. That the size is exactly the clock speed.


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
    # <<  TODO agents messages
    #
    # 1 stopping
    # 2 stopping
    # 2 received stop signal
    # 1 received stop signal
    # all 2 schedulers stopped