import logging
import time
from collections import deque
from maslite import Agent, AgentMessage, Scheduler, SchedulerException

LOG_LEVEL = logging.INFO

SKIP_CLOCK_TESTS = True


class TestAgent(Agent):
    def __init__(self):
        super().__init__()
        self.count_updates = 0
        self.count_setups = 0
        self.count_teardowns = 0

    def setup(self):
        self.count_setups += 1

    def update(self):
        self.count_updates += 1
        if self.keep_awake:
            self.pause()
            self.keep_awake = False

    def teardown(self):
        self.count_teardowns += 1


def test_message():
    msg = AgentMessage(1)
    assert msg.sender == 1
    assert msg.receiver is None
    assert msg.topic is AgentMessage.__name__
    assert isinstance(msg.uuid, int)

    msg.sender = 1  # test setattr
    msg.receiver = 2  # test setattr
    msg_cp = msg.copy()
    assert id(msg) != id(msg_cp)
    msg.topic = 3

    try:
        msg.uuid = 123
        assert False, "setting uuid after initiation is not permitted."
    except ValueError:
        assert True


def tests_message_exchange():
    a = Agent()
    assert isinstance(a.inbox, deque)
    assert a.uuid is not None
    b = Agent(uuid='this')
    assert b.uuid == 'this'
    assert isinstance(a.keep_awake, bool)

    try:
        a.uuid = 123
        assert False, "setting uuid after initiation is not permitted."
    except ValueError:
        assert True

    print(str(a))
    print(a.__repr__())

    m = AgentMessage(1, 1, 1)
    try:
        a.send(m)
        assert False
    except AssertionError:
        assert True

    assert a.messages is False
    a.inbox.append(m)
    assert a.messages is True

    m2 = a.receive()
    assert m2 == m

    m3 = a.receive()
    assert m3 is None

    assert hasattr(a, 'setup')
    assert callable(a.setup)

    try:
        a.update()
        assert False
    except NotImplementedError:
        assert True

    assert hasattr(a, 'teardown')
    assert callable(a.teardown)

    try:
        a.set_alarm(1, None, True, True)
        raise Exception("!")
    except AssertionError:
        assert True

    try:
        a.subscribe("this")
        raise Exception("!")
    except AssertionError:
        assert True


def tests_add_to_scheduler():
    s = Scheduler()
    a = Agent()
    assert callable(a.setup)
    s.add(a)
    assert callable(a.teardown)
    s.remove(a)

    a = TestAgent()
    s.add(a)
    assert a.count_setups == 1
    assert a.get_subscription_topics() == s.get_subscription_topics(), "these should be the same"

    assert a.uuid in a.get_subscription_topics()
    assert a.__class__.__name__ in a.get_subscription_topics()
    a.unsubscribe(a.__class__.__name__)
    assert a.uuid in a.get_subscription_topics()
    assert a.__class__.__name__ not in a.get_subscription_topics()
    assert a.uuid in a.get_subscriber_list(a.uuid)
    a.subscribe(a.__class__.__name__)
    assert a.__class__.__name__ in a.get_subscription_topics()

    assert a.messages is False
    m = AgentMessage(sender=a, receiver=a)
    assert m.sender == a.uuid
    assert m.receiver == a.uuid
    a.send(m)
    assert m in s.mail_queue
    s.process_mail_queue()
    assert m in a.inbox
    assert a.messages is True
    m2 = a.receive()
    assert m is m2
    assert m.uuid == m2.uuid
    # note for above: When the message is "sent" the uuid should not change.
    # however when the message is broadcast the uuid CAN change as new messages are made from the original.
    m3 = a.receive()
    assert m3 is None
    assert a.messages is False
    start = time.time()
    a.set_alarm(alarm_time=1, alarm_message=None, relative=True)
    s.run()
    end = time.time()
    assert end-start < 1, "scheduler didn't ignore the setting drop alarm if idle."
    assert a.count_updates == 1, a.count_updates
    assert a.count_setups == 1
    assert a.count_teardowns == 0

    # test the pause methods.
    s.run()
    assert a.count_updates == 1  # previous scheduler ended with setting alarm to update.
    s.run()
    assert a.count_updates == 1  # nothing has happened.

    # when the scheduler runs update with keep_awake == True, the agent will press "pause".
    a.keep_awake = True
    s.run()
    assert a.count_updates == 2
    s.remove(a)
    assert a.count_teardowns == 1

    s.add(a)
    assert a.count_setups == 2
    b = TestAgent()
    a.add(b)
    assert b.uuid in s.agents
    assert b.uuid in a.get_subscription_topics()

    try:
        a.add(b)
        raise Exception("!")
    except SchedulerException:
        assert True

    a.remove(b.uuid)
    assert b.uuid not in s.agents
    assert b.uuid not in a.get_subscription_topics()
    a.add(b)

    s.run()
    assert len(s.needs_update) == 0

    m4 = AgentMessage(sender=a, receiver=b)
    a.send(m4)
    s.run(iterations=1)
    assert m4 in b.inbox
    _ = b.receive()
    start = time.time()
    s.run(seconds=0.30, pause_if_idle=False)
    end = time.time()
    assert 0.295 < end - start < 0.305

    b.subscribe(topic="magic")
    m5 = AgentMessage(sender=a, topic="magic")
    m5.payload = "the secret sauce"
    a.send(m5)
    s.run()
    assert b.messages is True
    m5_cp = b.receive()
    assert m5_cp.sender == a.uuid
    assert hasattr(m5_cp, "payload"), "deepcopy should have added this!"
    assert m5_cp.payload == m5.payload

    alarm_msg = AgentMessage(sender=a, receiver=a, topic="Alarm!!!")

    a.set_alarm(alarm_time=1, alarm_message=alarm_msg, relative=True, ignore_alarm_if_idle=False)
    assert len(s.alarms) == 1
    start = time.time()
    s.run(clear_alarms_at_end=True)
    end = time.time()
    assert 0.95 < end-start < 1.05
    assert len(s.alarms) == 0
    alarm = a.receive()
    assert alarm_msg.topic == alarm.topic

    random_id = 2134565432
    m6 = AgentMessage(sender=a, receiver=random_id)
    a.send(m6)
    assert random_id not in s.agents

    m7 = AgentMessage(sender=a, topic=a.__class__.__name__)
    m7.payload = "copy test"
    a.send(m7)
    s.run()
    m7_cp = a.receive()
    assert m7_cp.payload == m7.payload
    m7_cp = b.receive()
    assert m7_cp.payload == m7.payload

    a.log(msg="test done")


def test_basic_message_abuse():
    s = Scheduler()
    a = Agent(uuid=1)
    b = Agent(uuid=2)
    c = Agent(uuid=3)
    for i in [a, b, c]:
        s.add(i)
        i.subscribe('test')

    with open(__file__, 'r') as fo:
        msg = AgentMessage(a, None, topic='test')
        msg.content = fo
        a.send(msg)
        try:
            s.process_mail_queue()
            assert False, "sending an open file handle is not permitted."
        except SchedulerException:
            assert True


class PingPongBall(AgentMessage):
    def __init__(self, sender, receiver, topic='ping'):
        super().__init__(sender=sender, receiver=receiver, topic=topic)


class PingPongPlayer(Agent):
    def __init__(self):
        super().__init__()
        self.operations['ping'] = self.hit
        self.operations['pong'] = self.hit
        self.operations['smash'] = self.loose
        self.outcome = None
        self.update_count = 0

    def setup(self):
        pass

    def teardown(self):
        print(self.outcome)

    def update(self):
        self.update_count += 1
        if self.messages:
            msg = self.receive()
            ops = self.operations.get(msg.topic)
            ops(msg)

    def hit(self, msg):
        assert isinstance(msg, PingPongBall)
        msg.sender, msg.receiver = msg.receiver, msg.sender
        if self.update_count < 5:
            if msg.topic == 'ping':
                msg.topic = 'pong'
            else:
                msg.topic = 'ping'
        else:
            msg.topic = 'smash'
            self.outcome = "won!"
        self.send(msg)

    def loose(self, msg):
        self.outcome = "beaten!"

    def serve(self, opponent):
        ball = PingPongBall(sender=self, receiver=opponent)
        self.send(ball)


def test_ping_pong_tests():
    s = Scheduler()
    player_a = PingPongPlayer()
    player_b = PingPongPlayer()
    s.add(player_a)
    s.add(player_b)
    player_a.serve(opponent=player_b)
    s.run()
    assert player_a.update_count == 5
    assert player_a.outcome == "won!"
    assert player_b.update_count == 5
    assert player_b.outcome != "won!"


def test_scheduling_demo():
    from demos.scheduling import test01
    test01()


def test_auction_demo():
    from demos.auction_model import test06
    test06()


