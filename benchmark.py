from maslite import Agent, Scheduler, AgentMessage

class Msg(AgentMessage):
    def __init__(self, sender, receiver=None, topic=None):
        super().__init__(sender, receiver, topic)
        self.value = 0

class A(Agent):
    def __init__(self, uuid=None):
        super().__init__(uuid)
        
    def update(self):
        if self.messages:
            m = self.receive()
            assert isinstance(m, Msg)
            m.value += 1
            m.receiver, m.sender = m.sender, m.receiver
            self.send(m)


if __name__ == "__main__":
    s = Scheduler()
    a = A()
    b = A()
    s.add(a)
    s.add(b)
    m = Msg(a,b)
    a.send(m)
    s.run(seconds=10)
    print(f"{m.value/10:,} messages/second")

    # :~$ python3.9 benchmarks.py
    # 480,440.9 messages/second

    # :-$ pypy3 benchmarks.py
    # 6,441,251.9 messages/second
    
