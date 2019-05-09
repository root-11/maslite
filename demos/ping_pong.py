from maslite import Agent, AgentMessage, Scheduler
from collections import deque
import time
""" Provides a demonstration of the ping-pong pattern between two
agents with priority inbox, who use the message topic as signal.
"""


class PingPongPlayer(Agent):
    def __init__(self):
        super().__init__()
        self.operations.update({'ping': self.pingpong,
                                'pong': self.pingpong})

    def setup(self):
        pass

    def teardown(self):
        pass

    def update(self):
        while self.messages:
            msg = self.receive()
            operation = self.operations.get(msg.topic)
            if operation is not None:
                operation(msg)

    def pingpong(self, msg):
        assert isinstance(msg, PingPongBall)
        msg.hit()
        self.send(msg)


class PingPongBall(AgentMessage):
    def __init__(self, sender, receiver):
        super().__init__(sender=sender, receiver=receiver, topic='ping')

    def hit(self):
        if self.topic in {'None', 'pong'}:
            self.topic = 'ping'
        else:
            self.topic = 'pong'
        # swopping sender and receiver.
        self.sender, self.receiver = self.receiver, self.sender


def demo():
    s = Scheduler()
    player1 = PingPongPlayer()
    s.add(player1)
    player2 = PingPongPlayer()
    s.add(player2)
    ball = PingPongBall(sender=player1, receiver=player2)
    player1.inbox.append(ball)
    response = None
    while response != 'q':
        response = input("How many passes do you want to play? : [integer]")
        try:
            turns = int(response)
        except ValueError:
            print("'{}' is not an integer. Try again or hit 'q' to quit".format(response))
            continue
        if abs(turns) > 0:
            s.run(iterations=abs(turns))
            response = None


def test00():
    s = Scheduler()
    player1 = PingPongPlayer()
    s.add(player1)
    player2 = PingPongPlayer()
    s.add(player2)
    ball = PingPongBall(sender=player1, receiver=player2)
    player1.inbox.append(ball)
    turns = 10000
    t_start = time.time()
    s.run(iterations=abs(turns))
    t_end = time.time()
    print("{} turns took {} sec ~ {} turns/sec".format(turns, t_end-t_start, round(turns / (t_end-t_start))))

if __name__ == "__main__":
    test00()
