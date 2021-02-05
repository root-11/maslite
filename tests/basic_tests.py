import logging
import time
from collections import deque
from maslite import Agent, AgentMessage, Scheduler, SchedulerException, MailingList

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


class TestMessage(AgentMessage):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def copy(self):
        return TestMessage(self.sender, self.receiver)


def test_message():
    msg = TestMessage(1)
    assert msg.sender == 1
    assert msg.receiver is None
    assert msg.topic is TestMessage.__name__

    msg.sender = 1  # test setattr
    msg.receiver = 2  # test setattr
    msg_cp = msg.copy()
    assert id(msg) != id(msg_cp)
    msg.topic = 3


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
    except TypeError:
        assert True

    try:
        a.subscribe("this")
        raise Exception("!")
    except AssertionError:
        assert True


def test_subscriptions():
    m = MailingList()

    m.subscribe(1, 1)
    m.subscribe(1, topic="A")
    assert m.get_subscriber_list(target=1) == {1}
    assert m.get_subscriber_list(topic='A') == {1}

    m.subscribe(2, target=1, topic='B')
    assert m.get_subscriber_list(target=1, topic='B') == {2}

    assert m.get_subscriber_list(target=1) == {1, 2}

    m.subscribe(3, target=1)
    assert m.get_subscriber_list(target=1) == {1, 2, 3}

    assert m.get_subscriber_list(topic='A') == {1}
    assert m.get_subscriber_list(topic='C') == set()
    assert m.get_subscriber_list(topic='B') == set()

    m.subscribe(4, 1, 'Z')
    m.unsubscribe(4)  # mailing list doesn't care, but scehduler will complain.


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
    a.unsubscribe(topic=a.__class__.__name__)
    assert a.uuid in a.get_subscription_topics()
    assert a.__class__.__name__ not in a.get_subscription_topics()
    assert a.uuid in a.get_subscriber_list(a.uuid)
    a.subscribe(topic=a.__class__.__name__)
    assert a.__class__.__name__ in a.get_subscription_topics()

    assert a.messages is False
    m = TestMessage(sender=a, receiver=a)
    assert m.sender == a.uuid
    assert m.receiver == a.uuid
    a.send(m)
    assert m in s.mail_queue
    s.process_mail_queue()
    assert m in a.inbox
    assert a.messages is True
    m2 = a.receive()
    assert m is m2
    m3 = a.receive()
    assert m3 is None
    assert a.messages is False
    s.run()
    start = time.time()
    alarm_mesage = TestMessage(a, a)
    a.set_alarm(alarm_time=1000000000, alarm_message=alarm_mesage)
    s.run()
    end = time.time()
    assert end - start < 1, "scheduler didn't ignore the setting drop alarm if idle."
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

    m4 = TestMessage(sender=a, receiver=b)
    a.send(m4)
    s.run(iterations=1)
    assert m4 in b.inbox
    _ = b.receive()
    start = time.time()
    s.run(seconds=0.30, pause_if_idle=False)
    end = time.time()
    assert 0.295 < end - start < 0.315, end - start

    alarm_msg = TestMessage(sender=a, receiver=a, topic="Alarm!!!")

    a.set_alarm(alarm_time=1, alarm_message=alarm_msg, relative=True, ignore_alarm_if_idle=False)
    assert len(s.clock.alarm_time) == 1
    start = time.time()
    s.run(clear_alarms_at_end=True, pause_if_idle=True)
    end = time.time()
    assert 0.95 < end - start < 1.05
    assert len(s.clock.alarm_time) == 0
    alarm = a.receive()
    assert alarm_msg.topic == alarm.topic

    random_id = 2134565432
    m6 = TestMessage(sender=a, receiver=random_id)
    a.send(m6)
    assert random_id not in s.agents

    a.log(msg="test done")


def test_basic_message_abuse():
    s = Scheduler()
    a = Agent(uuid=1)
    b = Agent(uuid=2)
    c = Agent(uuid=3)
    for i in [a, b, c]:
        s.add(i)
        i.subscribe('test')


class PingPongBall(AgentMessage):
    def __init__(self, sender, receiver, topic='ping'):
        super().__init__(sender=sender, receiver=receiver, topic=topic)


class PingPongPlayer(Agent):
    def __init__(self, limit=500):
        super().__init__()
        self.operations['ping'] = self.hit
        self.operations['pong'] = self.hit
        self.operations['smash'] = self.loose
        self.outcome = None
        self.update_count = 0
        self.limit = limit

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
        if self.update_count < self.limit:
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


def test_clear_alarms():
    s = Scheduler(real_time=False)
    a = TestAgent()
    b = TestAgent()
    s.add(a)
    s.add(b)
    # set alarms for a and b, then clear them
    alarm_msg = TestMessage(sender=a, receiver=a, topic="Alarm_b")
    alarm_msg_b = TestMessage(sender=b, receiver=b, topic="Alarm_b")
    a.set_alarm(alarm_time=1, alarm_message=alarm_msg, relative=True, ignore_alarm_if_idle=False)  # set for a by a
    a.set_alarm(alarm_time=1, alarm_message=alarm_msg_b, relative=True, ignore_alarm_if_idle=False)  # set for b by a
    b.set_alarm(alarm_time=2, alarm_message=alarm_msg_b, relative=True, ignore_alarm_if_idle=False)  # set for b by b
    assert s.clock.alarm_time == [1, 2]  # alarms set at 1 and 2
    assert a.list_alarms() == [(1, [alarm_msg])]
    assert b.list_alarms() == [(1, [alarm_msg_b]), (2, [alarm_msg_b])]
    b.clear_alarms()
    assert s.clock.alarm_time == [1]  # only the alarm for a at 1 remains
    a.clear_alarms(receiver=b.uuid)
    assert s.clock.alarm_time == [1]  # the alarm for a at 1 still remains
    b.clear_alarms(receiver=a.uuid)
    assert s.clock.alarm_time == []


def test_ping_pong_tests():
    s = Scheduler()
    limit = 5000
    player_a = PingPongPlayer(limit)
    player_b = PingPongPlayer(limit)
    s.add(player_a)
    s.add(player_b)
    player_a.serve(opponent=player_b)
    start = time.process_time()
    s.run()
    end = time.process_time()
    mps = (player_a.update_count + player_b.update_count) / (end-start)
    assert player_a.update_count == limit
    assert player_a.outcome == "won!"
    assert player_b.update_count == limit
    assert player_b.outcome != "won!"
    print(mps, "messages per second")


