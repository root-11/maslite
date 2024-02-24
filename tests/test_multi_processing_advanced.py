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
    def __str__(self) -> str:
        return "Stop signal"

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
        if self.route[-1] == current_agent:
            return None
        else:
            ix = self.route.index(current_agent)
            return self.route[ix+1]
    def __str__(self) -> str:
        return f"LogisticUnit:({self.id}): Route: {self.route}"

class TransferNotification(maslite.AgentMessage):
    def __init__(self, s, r):
        super().__init__(sender=s,receiver=r, direct=True)
    def __repr__(self) -> str:
        return super().__str__()
class TransferAcceptance(maslite.AgentMessage):
    def __init__(self, s, r):
        super().__init__(sender=s,receiver=r, direct=True)
    def __repr__(self) -> str:
        return super().__str__()
class Transfer(maslite.AgentMessage):
    def __init__(self, s, r, obj):
        super().__init__(sender=s,receiver=r, direct=True)
        self.obj = obj
    def __repr__(self) -> str:
        return super().__str__()

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
            print(f"{self.time:.4f}:Agent({self.uuid}): got: {msg}")
            ops = self.operations.get(msg.topic)
            ops(msg)
        self.inbox.clear()
    
    def transfer_notification(self, msg):
        assert isinstance(msg, TransferNotification)
        # all conveyors are operating at the same speed, so I spare the math.
        self.send(TransferAcceptance(self.uuid, r=msg.sender))
        print(f"{self.time:.4f}:Agent({self.uuid}) sending transfer acceptance to {msg.sender}")
    def transfer_acceptance(self,msg):
        assert isinstance(msg, TransferAcceptance)
        self.send(Transfer(s=self.uuid, r=msg.sender, obj=self.lu))
        self.lu = None
        print(f"{self.time:.4f}:Agent({self.uuid}) sending LU to {msg.sender}")
    
    def transfer(self, msg):
        assert isinstance(msg, Transfer)
        lu = msg.obj
        self.put(lu,leading_edge=0)

    def put(self, lu, leading_edge):
        print(f"{self.time:.4f}:Agent({self.uuid}): LU received")
        assert isinstance(lu, LogisticUnit)
        self.lu = lu
        
        zzz = (self.length - leading_edge) / self.speed

        next_agent_on_route = lu.next_agent(self.uuid)
        if next_agent_on_route is None:
            print(f"{self.time:.4f}:Agent({self.uuid}): LU arrived at destination: {lu}") 
            self._scheduler_api.stop()
        else:
            print(f"{self.time:.4f}:Agent({self.uuid}): set to transfer LU in {zzz} seconds")
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
    idx = count(start=1)
    def __init__(self, logger=None, mq_to_main=None, mq_to_self=None):
        super().__init__(logger)
        self.mq_to_main = mq_to_main
        self.mq_to_self = mq_to_self
        self.clock = None  # we need to set the remote controlled clock!
        self.name = next(self.idx)
        self.mail_queue = []

    def stop(self):
        self.mq_to_main.put(Stop())

    def process_mail_queue(self):  # -- OVERRIDE
        self.process_inter_proc_mail()

        for msg in self.mail_queue:
            assert isinstance(msg, maslite.AgentMessage)
            
            if msg.direct:
                if msg.receiver in self.agents:
                    print(f"{self.clock.time:.4f}:Scheduler({self.name}) sending local {msg}")
                    self.send_to_recipients(msg=msg, recipients=[msg.receiver])
                else:  # it's an inter proc message
                    print(f"{self.clock.time:.4f}:Scheduler{self.name} sending inter proc {msg}")
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
                print(f"{self.clock.time:.4f}:Scheduler({self.name}) interproc recieved {msg}")
                if isinstance(msg, maslite.AgentMessage):
                    self.mail_queue.append(msg)

                elif isinstance(msg, Stop):
                    print(f"{self.clock.time:.4f}:Scheduler({self.name}) received stop signal {msg}")
                    self._quit = True
                    break

                else:
                    raise Exception(f"{msg}")
            except queue.Empty:
                return

    # custom stripped down version on run.
    def run(self, seconds=None, iterations=None, pause_if_idle=True, clear_alarms_at_end=True):
        """ The main 'run' operation of the Scheduler.
        """
        # check all agents for messages (in case that someone on the outside has added messages).
        for agent in self.agents.values():
            if agent.inbox or agent.keep_awake:
                self.needs_update[agent.uuid] = True
        self.process_mail_queue()

        # The main loop of the scheduler:
        self._quit = False
        while not self._quit:  # _quit is set by method self.pause() and can be called by any agent.

            # update the agents. process.
            self.needs_update.update(self.has_keep_awake)
            for uuid in self.needs_update:
                agent = self.agents[uuid]
                agent.update()
                if agent.keep_awake:
                    self.has_keep_awake[uuid] = True
                elif uuid in self.has_keep_awake:
                    del self.has_keep_awake[uuid]
            self.needs_update.clear()

            # check any timed alarms.
            self.clock.tick()
            self.clock.release_alarm_messages()

            self.process_mail_queue()


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
        print(f"{self.clock.time:.4f}:Scheduler({self.name}) starting")
        self.process.start()

    def is_alive(self):
        return self.process.is_alive()

    @property
    def exitcode(self):
        return self.process.exitcode

    def add(self, agent):
        self.scheduler.add(agent)
        
    def run(self):
        # self.scheduler.clock.set_alarm(1_000_000, Transfer(1,2,3), False)
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
        if exc_tb:
            print(exc_tb)
            raise exc_type(exc_val)

    def new_partition(self):
        name = str(len(self.schedulers)+1)
        link = Link(name, ctx=self._ctx, global_time=self.global_time)  # communication link between mpmain and a scheduler.
        self.schedulers[name] = link
        return link.sub_proc
    
    def _start(self):
        print(f"{self.clock.now:.4f}: Starting sub-processes")
        procs = []
        for name, link in self.schedulers.items():
            assert isinstance(link, Link)

            for id in link.sub_proc.scheduler.agents.keys():
                self.agents[id] = name 

            link.start()
            procs.append(link)

        while not all(p.is_alive() is True for p in procs):
            sleep(0.01)  # wait for the OS to launch the procs.
        print(f"{self.clock.now:.4f}:All {len(self.schedulers)} started")

    def _stop(self):
        print(f"{self.clock.now:.4f}:Stopping sub-processes")
        procs = []
        for link in self.schedulers.values():
            assert isinstance(link,Link)

            link.to_sub_proc.put(Stop())  # send stop signal.
            procs.append(link)
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
        print(f"{self.clock.now:.4f}: All {len(self.schedulers)} schedulers stopped")

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
                    # print(f"{self.clock.now:.4f}:MPmain recieved {msg}")
                    if isinstance(msg, Stop):
                        self._quit = True
                        print(f"{self.clock.now:.4f}:MPmain received Stop")

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
    with MPmain(speed=1.0) as main:
    
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
    # platform linux -- Python 3.10.13[pypy-7.3.15-final], pytest-8.0.1, pluggy-1.4.0 -- /home/bjorn/github/maslite/.env-pypy3/bin/python3
    # cachedir: .pytest_cache
    # rootdir: /home/bjorn/github/maslite
    # collected 2 items                                                                                                                                                              

    # tests/test_multi_processing_advanced.py::test_multiprocessing Registering agent Conveyor 1
    # Registering agent Conveyor 2
    # Registering agent Conveyor 3
    # Registering agent Conveyor 4
    # 0.0000:Agent(1): LU received
    # 0.0000:Agent(1): set to transfer LU in 0.75 seconds
    # 0.0000: Starting sub-processes
    # 0.0000:Scheduler(1) starting
    # 0.0000:Scheduler(2) starting
    # 0.0982:All 2 started

    # --- starting intra proc "send" of LU

    # 0.8622:Scheduler(1) sending local 1 -> 2 TransferNotification
    # 0.8622:Agent(2): got: 1 -> 2 TransferNotification
    # 0.8622:Agent(2) sending transfer acceptance to 1
    # 0.8726:Scheduler(1) sending local 2 -> 1 TransferAcceptance
    # 0.8726:Agent(1): got: 2 -> 1 TransferAcceptance
    # 0.8726:Agent(1) sending LU to 2
    # 0.8770:Scheduler(1) sending local 1 -> 2 Transfer
    # 0.8770:Agent(2): got: 1 -> 2 Transfer
    # 0.8770:Agent(2): LU received

    # --- completed intra proc "send" of LU
    #     0.0148 seconds @ 20x speed
    #     0.0010 seconds @  1x speed.
    # === timedrift is marginal.

    # 0.8770:Agent(2): set to transfer LU in 2.0 seconds

    # --- starting inter proc "send" of LU
    # 2.8771:Scheduler1 sending inter proc 2 -> 3 TransferNotification
    # 3.0506:Scheduler(2) interproc recieved 2 -> 3 TransferNotification
    # 3.0506:Scheduler(2) sending local 2 -> 3 TransferNotification
    # 3.0506:Agent(3): got: 2 -> 3 TransferNotification
    # 3.0506:Agent(3) sending transfer acceptance to 2
    # 3.0936:Scheduler2 sending inter proc 3 -> 2 TransferAcceptance
    # 3.2079:Scheduler(1) interproc recieved 3 -> 2 TransferAcceptance
    # 3.2079:Scheduler(1) sending local 3 -> 2 TransferAcceptance
    # 3.2079:Agent(2): got: 3 -> 2 TransferAcceptance
    # 3.2079:Agent(2) sending LU to 3
    # 3.2354:Scheduler1 sending inter proc 2 -> 3 Transfer
    # 3.7260:Scheduler(2) interproc recieved 2 -> 3 Transfer
    # 3.7260:Scheduler(2) sending local 2 -> 3 Transfer
    # 3.7260:Agent(3): got: 2 -> 3 Transfer
    # 3.7260:Agent(3): LU received

    # --- completed inter proc "send" of LU in:
    #     0.0489 seconds @ 20x speed 
    #     0.0196 seconds @  1x speed.
    # === time drift is visible.


    # 3.7260:Agent(3): set to transfer LU in 2.0 seconds

    # --- starting intra proc "send" of LU

    # 5.7260:Scheduler(2) sending local 3 -> 4 TransferNotification
    # 5.7260:Agent(4): got: 3 -> 4 TransferNotification
    # 5.7260:Agent(4) sending transfer acceptance to 3
    # 5.7390:Scheduler(2) sending local 4 -> 3 TransferAcceptance
    # 5.7390:Agent(3): got: 4 -> 3 TransferAcceptance
    # 5.7390:Agent(3) sending LU to 4
    # 5.7460:Scheduler(2) sending local 3 -> 4 Transfer
    # 5.7460:Agent(4): got: 3 -> 4 Transfer
    # 5.7460:Agent(4): LU received

    # --- completed intra proc "send" of LU
    #     0.0200 seconds @ 20x speed
    #     0.0005 seconds @  1x speed.
    # === timedrift is marginal.

    # 5.7460:Agent(4): LU arrived at destination: LogisticUnit:(1): Route: [1, 2, 3, 4]
    # 5.7896:MPmain received Stop
    # 5.7917:Stopping sub-processes
    # 5.7776:Scheduler(1) interproc recieved Stop signal
    # 5.7776:Scheduler(1) received stop signal Stop signal
    # 5.7776:Scheduler(2) interproc recieved Stop signal
    # 5.7776:Scheduler(2) received stop signal Stop signal
    # 5.9999: All 2 schedulers stopped
    # PASSED
    # tests/test_multi_processing_advanced.py::test_time_resolution PASSED