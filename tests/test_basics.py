import logging
import time
from collections import deque
from maslite import Agent, AgentMessage, Scheduler, SchedulerException, MailingList

LOG_LEVEL = logging.INFO

SKIP_CLOCK_TESTS = True


class TrialAgent(Agent):
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


class TrialMessage(AgentMessage):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def copy(self):
        return TrialMessage(self.sender, self.receiver)


def test_message():
    msg = TrialMessage(1)
    assert msg.sender == 1
    assert msg.receiver is None
    assert msg.topic is TrialMessage.__name__

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
        a.subscribe(receiver="this")
        raise Exception("!")
    except AssertionError:
        assert True


def test_subscribe_and_unsubscribe():
    a, b, c, d = Agent(), Agent(), Agent(), Agent()

    s = Scheduler()
    for i in (a, b, c, d):
        s.add(i)

    a.subscribe(receiver=b.uuid, topic='fish')
    a.subscribe(receiver=c.uuid, topic='fish')
    # We do not: a.subscribe(d, 'fish')
    a.subscribe(topic='quantum physics')
    c.subscribe(receiver=a.uuid)

    assert a.get_subscriptions() == {None: {None: {"quantum physics": True},
                                            b.uuid: {"fish": True},
                                            c.uuid: {"fish": True}}}

    assert b.get_subscriptions() == {}

    assert c.get_subscriptions() == {None: {a.uuid: {None: True}}}

    c.unsubscribe(everything=True)
    d3 = c.get_subscriptions()
    assert not d3  # d3 is empty.

    c.subscribe(receiver=c.uuid)
    assert c.get_subscriptions() == {None: {c.uuid: {None: True}}}

    assert a.get_subscriptions() == {None: {None: {"quantum physics": True},
                                            b.uuid: {"fish": True},
                                            c.uuid: {"fish": True}}}


def test_subscriptions():
    m = MailingList()

    m.subscribe(subscriber=1, receiver=1)
    m.subscribe(subscriber=1, topic="A")
    assert m.get_subscriber_list(receiver=1) == [1]
    assert m.get_subscriber_list(topic='A') == [1]

    m.subscribe(subscriber=2, receiver=1, topic='B')
    assert m.get_subscriber_list(receiver=1, topic='B') == [2]

    assert m.get_subscriber_list(receiver=1) == [1]

    m.subscribe(subscriber=3, receiver=1)
    assert m.get_subscriber_list(receiver=1) == [1, 3]

    assert m.get_subscriber_list(topic='A') == [1]
    assert m.get_subscriber_list(topic='C') == []
    assert m.get_subscriber_list(topic='B') == []

    m.subscribe(subscriber=4, receiver=1, topic='Z')
    assert m.get_subscriber_list(receiver=1, topic='Z') == [4]
    m.unsubscribe(4, everything=True)  # mailing list doesn't care, but scheduler will complain.
    assert m.get_subscriber_list(receiver=1, topic='Z') == []


def test_message_and_broadcast_subscriptions():
    """ Test a group of subscribers all subscribed in different ways to a series of messages. """
    a, b, c = Agent(), Agent(), Agent()
    spy_a_b, spy_b_hello, spy_hello, spy_all_c = Agent(), Agent(), Agent(), Agent()

    s = Scheduler()
    for i in (a, b, c, spy_a_b, spy_b_hello, spy_hello, spy_all_c):
        s.add(i)

    msg_1 = TrialMessage(sender=a.uuid, receiver=b.uuid, topic='Hello')
    msg_2 = TrialMessage(sender=b.uuid, receiver=a.uuid, topic='Hello')
    msg_3 = TrialMessage(sender=b.uuid, receiver=c.uuid, topic='Hello')
    msg_4 = TrialMessage(sender=c.uuid, topic='Hello')  # a broadcast message
    msg_5 = TrialMessage(sender=a.uuid, receiver=b.uuid, topic='How are you?')  # a broadcast message

    # spies need to subscribe
    spy_a_b.subscribe(sender=a.uuid, receiver=b.uuid)  # spy_a_b subscribes to all messages sent from a to b
    spy_b_hello.subscribe(sender=b.uuid, topic='Hello')  # spy_b_hello subscribes to all messages sent from b with topic 'Hello'
    spy_hello.subscribe(topic='Hello')  # spy_hello subscribes to all messages with topic 'Hello'
    spy_all_c.subscribe(sender=c.uuid)  # spy_all_c subscribes to all messages sent to and from c
    spy_all_c.subscribe(receiver=c.uuid)  # spy_all_c subscribes to all messages sent to and from c

    s.mail_queue.append(msg_1)
    s.process_mail_queue()
    assert len(a.inbox) == len(c.inbox) == len(spy_b_hello.inbox) == 0
    # b received the message sent to it,
    # spy_a_b received the message because it was sent from a to b,
    # spy_hello received the message because it was sent with the topic 'Hello'
    assert len(b.inbox) == len(spy_a_b.inbox) == len(spy_hello.inbox) == 1
    b.inbox.clear()
    spy_a_b.inbox.clear()
    spy_hello.inbox.clear()

    s.mail_queue.append(msg_2)
    s.process_mail_queue()
    assert len(b.inbox) == len(c.inbox) == len(spy_a_b.inbox) == 0
    # a received the message because it was sent to it,
    # spy_b_hello received the message because it was sent from b with the topic 'Hello',
    # spy_hello received the message because it was sent with the topic 'Hello'
    assert len(a.inbox) == len(spy_b_hello.inbox) == len(spy_hello.inbox) == 1
    a.inbox.clear()
    spy_b_hello.inbox.clear()
    spy_hello.inbox.clear()

    s.mail_queue.append(msg_3)
    s.process_mail_queue()
    assert len(a.inbox) == len(b.inbox) == len(spy_a_b.inbox) == 0
    # c received the message because it was sent to it,
    # spy_b_hello received the message because it was sent from b with the topic 'Hello',
    # spy_hello received the message because it was sent with the topic 'Hello'
    # spy_all_c received the message because it was sent to c
    assert len(c.inbox) == len(spy_b_hello.inbox) == len(spy_hello.inbox) == len(spy_all_c.inbox) == 1
    c.inbox.clear()
    spy_b_hello.inbox.clear()
    spy_hello.inbox.clear()
    spy_all_c.inbox.clear()

    s.mail_queue.append(msg_4)
    s.process_mail_queue()
    assert len(a.inbox) == len(b.inbox) == len(c.inbox) == len(spy_a_b.inbox) == len(spy_b_hello.inbox) == 0
    # spy_hello received the broadcast because it was sent with the topic 'Hello'
    # spy_all_c received the broadcast because it was sent from c
    assert len(spy_hello.inbox) == len(spy_all_c.inbox) == 1
    spy_hello.inbox.clear()
    spy_all_c.inbox.clear()

    s.mail_queue.append(msg_5)
    s.process_mail_queue()
    assert len(a.inbox) == len(c.inbox) == len(spy_b_hello.inbox) == len(spy_hello.inbox) == 0
    # b received the message sent to it,
    # spy_a_b received the message because it was sent from a to b,
    assert len(b.inbox) == len(spy_a_b.inbox) == 1
    b.inbox.clear()
    spy_a_b.inbox.clear()


def tests_add_to_scheduler():
    s = Scheduler()
    a = Agent()
    assert callable(a.setup)
    s.add(a)
    assert callable(a.teardown)
    s.remove(a)

    a = TrialAgent()
    s.add(a)
    assert a.count_setups == 1
    assert a.get_subscription_topics() == s.get_subscription_topics(), "these should be the same"

    assert a.messages is False
    m = TrialMessage(sender=a, receiver=a)
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
    alarm_message = TrialMessage(a, a)
    a.set_alarm(alarm_time=1000000000, alarm_message=alarm_message)
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
    b = TrialAgent()
    a.add(b)
    assert b.uuid in s.agents

    try:
        a.add(b)
        raise Exception("!")
    except SchedulerException:
        assert True

    a.remove(b.uuid)
    assert b.uuid not in s.agents
    a.add(b)

    s.run()
    assert len(s.needs_update) == 0

    m4 = TrialMessage(sender=a, receiver=b)
    a.send(m4)
    s.run(iterations=1)
    assert m4 in b.inbox
    _ = b.receive()
    start = time.time()
    s.run(seconds=0.30, pause_if_idle=False)
    end = time.time()
    assert 0.295 < end - start < 0.315, end - start

    alarm_msg = TrialMessage(sender=a, receiver=a, topic="Alarm!!!")

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
    m6 = TrialMessage(sender=a, receiver=random_id)
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
        i.subscribe(receiver='test')


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
    a = TrialAgent()
    b = TrialAgent()
    s.add(a)
    s.add(b)
    # set alarms for a and b, then clear them
    alarm_msg = TrialMessage(sender=a, receiver=a, topic="Alarm_b")
    alarm_msg_b = TrialMessage(sender=b, receiver=b, topic="Alarm_b")
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


def test_clear_alarms_by_topic():
    s = Scheduler(real_time=False)
    a = TrialAgent()
    s.add(a)
    msg1 = TrialMessage(sender=a, receiver=a, topic='1')
    msg2 = TrialMessage(sender=a, receiver=a, topic='2')
    msg3 = TrialMessage(sender=a, receiver=a, topic='3')
    a.set_alarm(alarm_time=1, alarm_message=msg1, relative=True, ignore_alarm_if_idle=False)
    a.set_alarm(alarm_time=3, alarm_message=msg2, relative=True, ignore_alarm_if_idle=False)
    a.set_alarm(alarm_time=1, alarm_message=msg3, relative=True, ignore_alarm_if_idle=False)
    assert s.clock.alarm_time == [1, 3]
    assert s.clock.clients_to_wake_up == {1: {a.uuid: True}, 3: {a.uuid: True}}
    a.clear_alarms(receiver=a.uuid, topic='1')
    assert s.clock.alarm_time == [1, 3], s.clock.alarm_time
    a.clear_alarms(receiver=None, topic='3')
    assert s.clock.list_alarms(a.uuid) == [(3, [msg2])]
    assert s.clock.clients_to_wake_up == {3: {a.uuid: True}}


def test_run_scheduler_until():
    # first run on SimulationClock with no limit
    s = Scheduler(real_time=False)
    a = TrialAgent()
    s.add(a)
    msg1 = TrialMessage(sender=a, receiver=a, topic='1')
    msg2 = TrialMessage(sender=a, receiver=a, topic='2')
    msg3 = TrialMessage(sender=a, receiver=a, topic='3')
    a.set_alarm(alarm_time=1, alarm_message=msg1, relative=True, ignore_alarm_if_idle=False)
    a.set_alarm(alarm_time=1.5, alarm_message=msg2, relative=True, ignore_alarm_if_idle=False)
    a.set_alarm(alarm_time=3, alarm_message=msg3, relative=True, ignore_alarm_if_idle=False)
    s.run()
    assert s.clock.time == 3
    assert not s.clock.list_alarms(a.uuid)

    # second run on simulation clock until 2 seconds (missing the alarm at 3 seconds)
    s = Scheduler(real_time=False)
    a = TrialAgent()
    s.add(a)
    msg1 = TrialMessage(sender=a, receiver=a, topic='1')
    msg2 = TrialMessage(sender=a, receiver=a, topic='2')
    msg3 = TrialMessage(sender=a, receiver=a, topic='3')
    a.set_alarm(alarm_time=1, alarm_message=msg1, relative=True, ignore_alarm_if_idle=False)
    a.set_alarm(alarm_time=1.5, alarm_message=msg2, relative=True, ignore_alarm_if_idle=False)
    a.set_alarm(alarm_time=3, alarm_message=msg3, relative=True, ignore_alarm_if_idle=False)
    s.run(seconds=2)
    assert s.clock.time == 2
    assert s.clock.list_alarms(a.uuid) == [(3, [msg3])]

    # third, run on real time clock
    s = Scheduler(real_time=True)
    a = TrialAgent()
    s.add(a)
    msg1 = TrialMessage(sender=a, receiver=a, topic='1')
    start_time = time.time()
    a.set_alarm(alarm_time=start_time + 10, alarm_message=msg1, relative=True, ignore_alarm_if_idle=False)
    s.run(seconds=2)
    end_time = time.time()
    assert round(end_time - start_time, 0) == 2


def test_run_until_multiple_successive_runs():
    """ Run multiple short runs, with the time continuing.
    """
    s = Scheduler(real_time=False)
    a = TrialAgent()
    s.add(a)
    for i in range(3, 22, 3):
        msg = TrialMessage(sender=a, receiver=a, topic=f"{i}_msg")
        a.set_alarm(alarm_time=i, alarm_message=msg, relative=True, ignore_alarm_if_idle=False)

    for i in range(2, 22, 2):
        s.run(seconds=2, clear_alarms_at_end=False)
        assert s.clock.time == i

    s.run()
    assert s.clock.time == 21


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
