import queue
import multiprocessing
from multiprocessing.context import BaseContext
from itertools import count
from random import choice
from time import process_time, sleep
import platform
default_context = "spawn" if platform.system() != 'Linux' else "fork"

class Stop:
    """ a simple stop signal."""

class ChainMsg:
    """ A standard message 
    we send this message around for multiple agents to sign.
    Once all the agents have signed it, a contract message
    is created and sent to the main process.
    """
    ids = count(start=1)
    def __init__(self,s,r) -> None:
        self.id = next(ChainMsg.ids)
        self.s = s
        self.r = r
        self.signature = []
    def __str__(self) -> str:
        return f"Msg:({self.id} - {self.s}:{self.r}): {self.signature}"


class Contract:
    def __init__(self, s, signatures) -> None:
        self.s = s
        self.r = "nobody"
        self.signatures = signatures
    def __str__(self) -> str:
        return f"{self.s} received signatures from eveyone."

class Link:
    """ scaffolding to keep queues and subprocess together """
    def __init__(self,name, ctx) -> None:
        self.to_mp = ctx.Queue()
        self.to_proc = ctx.Queue()
        self.scheduler = MPScheduler(ctx=ctx, mq_to_main=self.to_mp, mq_to_self=self.to_proc, name=name)
    def start(self):
        self.scheduler.start()
    def is_alive(self):
        return self.scheduler.is_alive()
    @property
    def exitcode(self):
        return self.scheduler.exitcode

class MPmain:
    """ The main process for inter-process message exchange """
    def __init__(self, context=default_context) -> None:
        self._ctx = multiprocessing.get_context(context)
        
        self.links = []
        self.schedulers = {}
        
        self.agents = {}  # agent.id: proc.id
        self.finished = []
        self._quit = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):  # signature requires these, though I don't use them.
        self._stop()

    def new_partition(self):
        name = str(len(self.schedulers)+1)
        link = Link(name, ctx=self._ctx)  # communication link between mpmain and a scheduler.
        self.schedulers[name] = link
        return link.scheduler
    
    def _start(self):
        procs = []
        for name, link in self.schedulers.items():
            for id in link.scheduler.agents.keys():
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
            link.to_proc.put(Stop())  # send stop signal.
            procs.append(link)
            print(f"{link.scheduler.name} stopping")
        while any(p.is_alive() for p in procs):
            sleep(0.01)  # wait until all subprocesses have stopped.

        # multiprocessing can't shut down until all message queues are 
        # empty, so we need to purge the system.
        for link in self.schedulers.values():
            assert isinstance(link, Link)
            while not link.to_mp.empty:
                _ = link.to_mp.get_nowait()
            while not link.to_proc.empty:
                _ = link.to_proc.get_nowait()
        print(f"all {len(self.schedulers)} schedulers stopped")

    def run(self, timeout=3):
        self._start()
        try:
            while not self._quit:
                if process_time() > timeout:
                    return
                self.process_mail_queue()
        except KeyboardInterrupt:
            pass

    def process_mail_queue(self):
        for name, link in self.schedulers.items():
            for _ in range(link.to_mp.qsize()):
                try:
                    msg = link.to_mp.get_nowait()
                    print(msg)
                    if isinstance(msg, Contract):
                        self.finished.append(msg.s)
                        if set(self.finished) == set(self.agents):
                            self._quit = True
                    elif isinstance(msg, ChainMsg):
                        link_name = self.agents[msg.r]
                        link = self.schedulers[link_name]
                        link.to_proc.put(msg)
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

class Agent:
    def __init__(self, id, peers, everyone) -> None:
        self.id = id
        if id in peers:
            raise ValueError("that's silly... ")
        self.peers = peers
        self.everyone = set(everyone)
        self.inbox = []
        self.scheduler = None

    def update(self):
        for msg in self.inbox:
            print(msg)
            self.new_message(msg)
        self.inbox.clear()
    
    def new_message(self, msg):
        msg.signature.append(self.id)
        if set(msg.signature) == self.everyone:
            # the message has been signed by everyone. 
            # Now make the contract.
            self.send(Contract(s=self.id, signatures=self.everyone))
        else:
            msg.s = self.id
            msg.r = choice(self.peers)
            self.send(msg)

    def send(self, msg):
        self.scheduler.mail_queue.append(msg)


class MPScheduler:
    def __init__(self, ctx:BaseContext, 
                 mq_to_main:multiprocessing.Queue,
                 mq_to_self:multiprocessing.Queue, 
                 name: str) -> None:
        self.ctx = ctx
        self.exit = ctx.Event()
        self.mq_to_main = mq_to_main
        self.mq_to_self = mq_to_self
        self.process = ctx.Process(group=None, target=self.run, name=name, daemon=False)
        self.name = name
        self._quit = False

        self.agents = {}
        self.mail_queue = []
        
    def start(self):
        print("starting")
        self.process.start()

    def is_alive(self):
        return self.process.is_alive()

    @property
    def exitcode(self):
        return self.process.exitcode

    def add(self, agent):
        print(f"adding agent {agent.id}")
        agent.scheduler = self
        self.agents[agent.id] = agent

    def update_agents(self):
        for agent in self.agents.values():
            if agent.inbox:
                agent.update()

    def process_mail_queue(self):
        for msg in self.mail_queue[:]:
            if msg.r in self.agents:  # if receiver is known ...
                agent = self.agents[msg.r]
                agent.inbox.append(msg)
            else:  # give it to main ...
                self.mq_to_main.put(msg)
        self.mail_queue.clear()

    def process_inter_proc_mail(self):
        while not self._quit:
            try:
                msg = self.mq_to_self.get_nowait()
                if isinstance(msg, ChainMsg):
                    self.mail_queue.append(msg)
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
            self.process_mail_queue()
            self.update_agents()


def test_multiprocessing():
    """ Demonstrates the multiprocessing where mpmain has two schedulers
    which each have two agents (4 agents in total).

    Each agent decides at random who to send a message to. 
    The demonstration stops when all messages have been signed by all agents.
    """
    with MPmain() as main:
    
        a1 = Agent(1,[2], everyone={1,2,3,4})
        a2 = Agent(2,[3], everyone={1,2,3,4})
        a3 = Agent(3,[4], everyone={1,2,3,4})
        a4 = Agent(4,[1], everyone={1,2,3,4})

        a1.inbox.append(ChainMsg(s=1, r=1))

        # simulation partition 1
        s1 = main.new_partition()
        s1.add(a1)
        s1.add(a2)

        # simulation partition 2
        s2 = main.new_partition()
        s2.add(a3)
        s2.add(a4)

        main.run()

if __name__ == "__main__":
    test_multiprocessing()
    # output:
    # -------------------------------
    # adding agent 1
    # adding agent 2
    # adding agent 3
    # adding agent 4
    # starting
    # 1 starting
    # starting
    # 2 starting
    # all 2 started
    # Msg:(1 - 1:1 []
    # Msg:(1 - 1:2): [1]
    # Msg:(1 - 2:3): [1, 2]
    # Msg:(1 - 2:3): [1, 2]
    # Msg:(1 - 3:4): [1, 2, 3]
    # 4 received signatures from eveyone.
    # 1 stopping
    # 2 stopping
    # 1 received stop signal
    # 2 received stop signal
    # all 2 schedulers stoppedS