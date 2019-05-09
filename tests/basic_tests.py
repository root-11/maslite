import logging
import time
from random import randint
from uuid import uuid4
from collections import deque
from maslite import AddNewAgent, RemoveAgent
from maslite import Agent, AgentMessage, AlarmMessage, PauseMessage
from maslite import GetSubscriptionTopicsMessage, Clock, Scheduler, Sentinel
from maslite import SetTimeAndClockSpeedMessage, StartMessage, StopMessage
from maslite import SubscribeMessage, UnSubscribeMessage, GetSubscribersMessage
from tests.importable_agents_for_tests import TestAgent

LOG_LEVEL = logging.INFO

SKIP_CLOCK_TESTS = True


def test_basic_agent_creation():
    """ Test basic object creation including all messages"""
    a = Agent()
    assert hasattr(a, "uuid")
    assert hasattr(a, "inbox")
    assert hasattr(a, "outbox")
    assert a.uuid
    assert isinstance(a.inbox, deque)
    assert isinstance(a.outbox, deque)
    assert hasattr(a, "receive")
    assert callable(a.receive)
    assert hasattr(a, "messages")
    _ = str(a)
    assert a.keep_awake is False, "the default agent should be asleep"
    assert hasattr(a, "__str__")
    assert "UUID" in str(a).upper()
    assert hasattr(a, "__repr__")
    print(a)

    try:
        a.setup()
    except NotImplementedError:
        assert True

    try:
        a.update()
    except NotImplementedError:
        assert True

    try:
        a.teardown()
    except NotImplementedError:
        assert True


def test_uuid_settings():
    uuid = uuid4()
    a = Agent(uuid=uuid.int)
    try:
        a = Agent(uuid=uuid.hex)
        assert False, "this should have failed."
    except ValueError:
        assert True


def test_the_test_agent():
    a = TestAgent()
    assert a.is_setup() is False
    a.receive()  # forcing receive in stupidity and making sure that the exception is caught and handled gracefully.

    before = len(a.outbox)
    a.unsubscribe(topic="007")
    after = len(a.outbox)
    assert (
        after - before == 1
    ), "An unsubscribe message should have ended up in the agents outbox."


def test_of_sentinel_creation():
    s = Sentinel()
    assert hasattr(s, "uuid")
    s2 = Sentinel(uuid=123456)
    assert not s is s2
    assert s.uuid != s2.uuid


def test_essential_message_functions():
    a = TestAgent()
    basic_msg = AgentMessage(sender=a, receiver=a, topic="test")
    assert basic_msg.receiver == a.uuid
    assert basic_msg.sender == a.uuid
    assert basic_msg.topic == "test"
    assert isinstance(basic_msg.uuid, int)
    try:
        a.uuid = "hahaha"
        assert False, "UUID cannot be set once the object has been instantiated"
    except ValueError:
        assert True

    assert hasattr(basic_msg, "copy")
    copy = basic_msg.copy()
    assert copy is not basic_msg, "they should be different objects"
    for k, v in basic_msg.__dict__.items():
        assert hasattr(
            copy, k
        ), "the copy of the basic message doesn't have the attr {}".format(k)
        assert (
            getattr(copy, k) == v
        ), "the value on the copy of the message is not the same {} != {}".format(
            getattr(copy, k), v
        )
    # test the update function with a non-specific message
    a.inbox.append(basic_msg)
    a.run()
    a._quit = True
    a.run()
    basic_msg.sender = 44
    assert basic_msg.sender == 44
    basic_msg.sender = None
    assert basic_msg.sender is None
    basic_msg.topic = "random topic"
    assert basic_msg.topic == "random topic"


def check_that_all_messages_can_be_created():
    """
    All the messages below should be able to create without errors.
    """
    a = Agent()
    messages = []
    add = messages.append
    basic_msg = AgentMessage(sender=a, receiver=a, topic="test")
    add(basic_msg)
    add(StartMessage(sender=a))
    add(AlarmMessage(sender=a, receiver=a, alarm_time=44, alarm_message=messages[0]))
    add(AlarmMessage(sender=a, receiver=a, alarm_time=50))
    add(PauseMessage(sender=a, receiver=a))
    add(SetTimeAndClockSpeedMessage(sender=a, new_time=123, new_clock_speed=1.0))
    add(SetTimeAndClockSpeedMessage(sender=a, new_time=None, new_clock_speed=5.0))
    add(SetTimeAndClockSpeedMessage(sender=a, new_time=123, new_clock_speed=None))
    add(SetTimeAndClockSpeedMessage(sender=a))
    add(StartMessage(sender=a, receiver=a))
    add(StopMessage(sender=a, receiver=a))
    add(SubscribeMessage(sender=a, receiver=a, subscription_topic="Tests"))
    usm = UnSubscribeMessage(sender=a, receiver=a, subscription_topic="Testing")
    assert usm.subscription_topic == "Testing"
    add(usm)
    add(GetSubscriptionTopicsMessage(sender=a, receiver=a, subscription_topics="tests"))
    add(GetSubscribersMessage(sender=a, receiver=a, subscription_topic="Testing"))

    for msg in messages:
        _ = str(msg)
    print("Message tests complete")


def test_clocks_attrs():
    s = Scheduler()
    s.setup()
    hasattr(s, "clock")
    assert isinstance(s.clock, Clock)
    assert s.clock.uuid in s.agents
    assert hasattr(s.clock, "setup")
    s.clock.setup()
    s.clock.update()
    s.clock.set_time_using_msg(
        SetTimeAndClockSpeedMessage(
            sender=s,
            receiver=None,
            new_time=randint(-10, 10),
            new_clock_speed=randint(1, 10),
        )
    )
    try:
        s.clock.time = "1970-01-01T00:00:00.000"
        assert False
    except AttributeError:
        assert True

    try:
        s.clock.clock_speed = "really fast"
        assert False, "this should fail"
    except ValueError:
        assert True

    assert 0.0 < s.clock.clock_frequency, s.clock.clock_frequency
    try:
        s.clock.clock_frequency = 40000
        assert False
    except ValueError:
        assert True
    s.clock.advance_time_to_next_timed_event(issue_stop_message_if_no_more_events=True)
    assert isinstance(
        s.clock.outbox[-1], PauseMessage
    ), "A pause message should have been issued."
    s.run(seconds=1)
    s.clock.teardown()
    assert not s.clock.is_setup()
    s.teardown()


def test_scheduler_teardown_with_junk():
    s = Scheduler()
    s.mail_queue.append("a non-AgentMessage")
    s.process_mail_queue()  # quietly dumps the broken message with a
    # log message stating "Discovered a faulty non-AgentMessage in the inbox. Message is dumped..."
    s.agents[123] = "this string"
    try:
        s.run(iterations=1)
        assert False, "running with non-agents won't work."
    except AssertionError:
        assert True

    try:
        s.teardown()
        assert False, "teardown with non-agents won't work."
    except AssertionError:
        assert True

    s = Scheduler()
    s.setup()
    s.remove(s.clock)  # doing this is very stupid so we'd better have a test for it.
    s.remove(s.clock)  # 2 x stupid doesn't make it smart.


def scheduler_and_clock_setup_test():
    """ Checking setup of the scheduler and clock """
    s = Scheduler()
    start_time = 10000
    s.set_time(start_time)
    a = TestAgent()
    s.add(a)
    s.run(iterations=1)
    assert s.time != 0, s.time
    assert s.time == start_time
    # time is now 10000. Ready!
    a.set_timed_alarm(5, relative=True)
    a.set_timed_alarm(12000, relative=False)  # should go off at 12000.

    time_steps = []
    iterations = 1
    for i in range(30):  # expected stop after 24 iterations.
        s.run(iterations=iterations)
        if s.message_count[-1] == 0:
            iterations = 3  # it takes 5 iterations to clear the 'idle'-queue.
        else:
            iterations = 1
        if a.time not in time_steps:
            time_steps.append(a.time)
        if len(time_steps) == 2:
            assert True
            return
    else:
        assert False, "The test should have finished in 24 iterations."


def test_that_the_scheduler_pauses_when_idle():
    """ run until idle """
    s = Scheduler()
    start = time.time()
    s.run(pause_if_idle=True)
    end = time.time()
    assert s.pause, "The scheduler should have paused"
    assert end - start < 1, "took too long."


def clock_tests():  # Clock tests
    """ Running basic clock tests"""
    if SKIP_CLOCK_TESTS:
        return
    test_duration = 1  # seconds
    configurations = [
        [0, 1],
        [10, 1],
        [100, 1],
        [1000, 1],
        [0, 2],
        [10, 2],
        [100, 2],
        [1000, 2],
        [10, 10],
    ]
    for set_time, speed in configurations:
        c = Clock(world_time=set_time, clock_speed=speed)
        c.run()
        start = c.time
        start_time = time.time()
        while time.time() < start_time + test_duration:
            if randint(0, 1):
                c.run()
            end = c.time
        end_time = time.time()
        elapsed_real_time = end_time - start_time
        elapsed_clock_time = (end - start) / speed
        tolerance = abs(elapsed_clock_time - elapsed_real_time)
        if tolerance != 0:
            hz = 1 / tolerance
        else:
            hz = 10 ** 6
        values = [
            "end-time: {}".format(end),
            "start-time: {}".format(start),
            "dt: {}".format(end - start),
            "clock-frq: {}".format((end - start) / speed),
            "clock-speed: {}".format(speed),
        ]
        logging.log(
            logging.DEBUG,
            "clock precision is around {} Hz with config: [{},{}] and values: \n\t{}".format(
                hz, set_time, speed, "\n\t".join(values)
            ),
        )
        print(".", end="", flush=True)


def tests_for_changing_clock_speeds():
    """ Running tests for adjusting the clock speed"""
    if SKIP_CLOCK_TESTS:
        return  # FIXME
    c = Clock()
    # assert c.time == 0.0, "launching the Clock shouldn't take 100 msecs'."
    assert isinstance(c.clock_frequency, float)  # check that the function works.
    assert isinstance(c.clock_speed, (int, float))
    assert isinstance(c.uuid, int)
    dummy_msg = AgentMessage(c)
    msg = AlarmMessage(sender=c, receiver=c, alarm_time=1.5, alarm_message=dummy_msg)
    c.set_alarm(msg)
    assert len(c.alarms) == 1, "the alam message should be here."
    c.run()  # c.run runs both: c.setup(), c.update(), c.teardown()
    start = time.time()
    while dummy_msg not in c.outbox:
        c.run()
    end = time.time()
    assert (
        1.45 < end - start < 1.55
    ), "The alarm message should be returned within 1.5 secs +/-10%"

    # react's to functions:
    timestamp = time.time() - 2  # setting the timestamp in the past to avoid sleeping.

    new_time = -10 ** 9  # setting time to the beginning of the universe.
    set_time_msg = SetTimeAndClockSpeedMessage(c, c, new_time=new_time)
    c.set_time_using_msg(set_time_msg)
    assert c.time < -10 ** 8, "Time should have been set back"

    # running the clock at a million times real-time.
    new_clock_speed = 10 ** 6
    set_time_msg = SetTimeAndClockSpeedMessage(
        c, c, new_time=c.time, new_clock_speed=new_clock_speed
    )
    c.set_time_using_msg(set_time_msg)
    assert (
        c.clock_speed == new_clock_speed
    ), "clock speed should be {}, but is {}".format(c.clock_speed, new_clock_speed)
    time_measurements = []
    start = c.time
    for i in range(4):
        time.sleep(1)
        end = c.time
        time_measurements.append(
            end - start
        )  # should be appx. 1 second each, which equals 10**6 seconds.
        start = end
    average = sum(time_measurements) / len(time_measurements)
    tolerance = 0.05
    assert (
        new_clock_speed * (1 - tolerance) < average < new_clock_speed * (1 + tolerance)
    ), "clock speed progressed at {}, whilst {} +/-{}% was expected".format(
        average, new_clock_speed, 100 * tolerance
    )

    try:
        c.time = "1970-01-01T00:00:00.000000"
        assert False, "The above usage of a timestring is invalid."
    except AttributeError:
        assert True
    except Exception:
        assert False, "The try/except should have raised an AttributeError."

    try:
        c.clock_speed = "fast"
        assert (
            False
        ), "Setting clock speed requires an integer or float. A string was passed"
    except ValueError:
        assert True

    try:
        msg = SetTimeAndClockSpeedMessage(sender=44, receiver=c, new_time="now")
        assert False, "The set time message's new_time does not accept a string."
    except AttributeError:
        assert True

    try:
        msg = SetTimeAndClockSpeedMessage(
            sender=44, receiver=c, new_time=time.time(), new_clock_speed="2x"
        )
        assert False, "The set time message's new_clock_speed does not accept a string."
    except AttributeError:
        assert True

    msg = AgentMessage(sender=1, receiver=Clock.__name__, topic="irrelevant topic")
    c.inbox.append(msg)
    try:
        c.update()  # nothing should change.
        assert True
    except Exception:
        assert False, "the clock should have ignored the message."


def one_to_one_mail_distribution_tests():
    """ Running mailman tests """
    s = Scheduler()
    s.setup()
    s.run(iterations=10)
    before = len(s.outbox)
    s.get_subscription_topics(
        GetSubscriptionTopicsMessage(sender=s, receiver=s, subscription_topics=s.uuid)
    )
    after = len(s.outbox)
    assert after - before == 1
    m = s.outbox[-1]
    assert isinstance(m, GetSubscriptionTopicsMessage)
    assert isinstance(m.subscription_topics, list)
    assert s.uuid == m.subscription_topics[0]

    s.get_subscription_topics(GetSubscriptionTopicsMessage(sender=s, receiver=s))
    m = s.outbox[-1]
    assert len(m.subscription_topics) > 1

    #
    s.get_subscriber_list(
        GetSubscribersMessage(sender=s, subscription_topic=s.clock.uuid)
    )
    m = s.outbox[-1]
    assert isinstance(m, GetSubscribersMessage)
    assert isinstance(m.subscribers, set)
    assert s.clock.uuid in m.subscribers
    # exercising the unsubscribe functions.
    s.mailing_lists[s.clock.uuid].add("1234567890")
    s.process_unsubscribe_message(
        UnSubscribeMessage(sender=s.clock, subscription_topic=s.clock.uuid)
    )
    s.mailing_lists[s.clock.uuid].remove("1234567890")
    # (below): A deliberate repeat unsubscribe triggers a keyerror that is handled gracefully.
    s.process_unsubscribe_message(
        UnSubscribeMessage(sender=s.clock, subscription_topic=s.clock.uuid)
    )
    # the mailing list is now empty and shold be purged.
    assert not s.clock.uuid in s.mailing_lists, s.mailing_lists

    s.process_unsubscribe_message(
        UnSubscribeMessage(sender=s.clock, subscription_topic=s.uuid)
    )
    # (above) is quietly dumped as an IndexError is raised.
    s.process_unsubscribe_message(
        UnSubscribeMessage(sender=s.clock, subscription_topic=None)
    )

    s.teardown()


def tests_for_mail_distributions_broadcast_functionality():
    """ Testing the mailmans broadcast functionality."""
    s = Scheduler(clock_speed=1.00000, pause_if_idle=True)
    agents = [TestAgent() for i in range(10)]
    for agent in agents:
        s.add(agent)
    agent_topic = agents[0].__class__.__name__
    spam_msg = AgentMessage(sender=s, receiver=None, topic=agent_topic)
    s.inbox.append(spam_msg)
    print("Mailman's broadcast functionality works...")
    s.run(iterations=5)
    # making a genuine agent message but injecting it into the mailmans subscribe method which will fail.

    # injecting an unsubscribe message for a topic that never was subscribed for.
    fake_unsub_msg = UnSubscribeMessage(sender=s, subscription_topic="black ninjas")
    s.inbox.append(fake_unsub_msg)
    s.run(iterations=5)

    sub_msg = SubscribeMessage(s, "black ninja's")
    s.inbox.append(sub_msg)
    s.run(iterations=5)

    topic = "fluffy poppies"
    get_subs_wrong_topic = GetSubscribersMessage(s, topic)
    assert get_subs_wrong_topic.subscribers == None
    s.inbox.append(get_subs_wrong_topic)
    s.run(iterations=5)

    # testing that remove agent works.

    dead_agent = [
        agent.uuid for agent in s.agents.values() if isinstance(agent, TestAgent)
    ][0]
    s.remove(dead_agent)
    s.stop()


def test_schedulers_remove_agent_function():
    s = Scheduler()
    a = TestAgent()
    s.add(a)
    an_agent_uuid = a.uuid
    s.remove(an_agent_uuid)
    s.run(iterations=1)
    for a in s.agents:
        if hasattr(a, "get_uuid"):
            if an_agent_uuid == a.uuid:
                assert False, "Hmm... This agent should have been removed..."
    s.stop()


def tests_schedulers_add_and_remove_funtions_using_messages():
    """ Test to add/remove agents using messages sent to the scheduler's class name."""
    s = Scheduler(clock_speed=1.00000, pause_if_idle=True)
    a = TestAgent()
    msg = AddNewAgent(sender=s, agent=a)
    s.inbox.append(msg)
    s.run(iterations=3)
    assert a.uuid in s.agents, "TestAgent class should be registered by now"
    s.run(iterations=10)
    assert (
        TestAgent.__name__ in s.mailing_lists.keys()
    ), "TestAgent class should be registered by now"
    msg = RemoveAgent(sender=s, agent_or_agent_uuid=a)
    s.inbox.append(msg)
    s.run(iterations=5)
    assert (
        TestAgent.__name__ not in s.agents
    ), "TestAgent class should be de-registered by now"
    s.stop()


def checking_the_schedulers_real_time_start_up_time():  # Single threaded scheduler tests.
    """ Running a single processor single threaded test of the scheduler. """
    s1 = Scheduler(clock_speed=1.00000, pause_if_idle=True)
    assert s1.clock.time < 0.2, "launching the Scheduler shouldn't take 200 msecs'."
    start = time.time()
    s1.run(seconds=1)  # one second !
    end = time.time()
    assert (
        0 < (end - start) < 1.5
    ), "the scheduler should have timedout in ~1 sec. Actual time was {}".format(
        end - start
    )


def Testing_the_schedulers_timed_stop_function():
    """ Testing the schedulers timed stop function. """
    s = Scheduler(clock_speed=1.00000, pause_if_idle=True)
    start = time.time()
    s.run(seconds=1)
    end = time.time()
    assert (
        end - start < 1.5
    ), "The scheduler was supposed to stop within a second. Apparently it didn't."
    s.stop()


def test_of_clock_scheduled_speed_changes():
    """
    Test 14 asserts that the clock jumps in time when the clock speed is
    set to None, whilst maintaining an exact progression of time.

    The test exercises the functions:
    - set clock_speed to None.
    - set_new_clock_speed_as_timed_event
    - set_pause_time
    - set_stop_time """
    start = time.time()
    s = Scheduler(clock_speed=None, pause_if_idle=True)
    s.clock.time = 0
    s.set_new_clock_speed_as_timed_event(start_time=0, clock_speed=None)
    s.set_pause_time(10)
    s.run(pause_if_idle=True)
    assert (
        s.clock.clock_speed is None
    ), "Clock speed doesn't seem to have been set to 'None'...!"
    assert 10 <= s.time <= 10.01, "Timing problem..!"
    s.set_stop_time(s.time + 100)
    s.run(clock_speed=None)
    end = time.time()
    tolerated_delay = 2.25  # FIXME!
    assert (
        end - start < tolerated_delay
    ), "The time progressed slower than expected: {} actual {}".format(
        tolerated_delay, end - start
    )
    s.stop()


def test_of_the_clocks_ability_to_jump_in_time_to_next_event():
    """ clock.advance_to_next_event """
    c = Clock(clock_speed=None)
    dt = 2
    now = c.time
    c.set_alarm_clock(
        alarm_time=now + dt,
        alarm_message=AgentMessage(sender=c, receiver=c, topic="hello world"),
    )
    c.advance_time_to_next_timed_event()
    after = c.time
    assert (
        dt == after - now
    ), "Error: dt was {}, whilst c.now is {} and now was {}".format(dt, after, now)


def Testing_start_and_pause_of_the_scheduler():
    """ Testing start and pause of the scheduler

    The problem is described below, but the test assures that time only progresses
    whilst the scheduler is running.

    If the clock continues to tick whilst the scheduler is in state=='paused', it
    becomes harder to debug as timed events needs to be monitored in real-time.

    # Example of bug:
    # >>> s = Scheduler()
    # 2017-02-11 15:40:31,334 - INFO - Scheduler is running with uuid: 33892713549718271865085484516606075993
    # 2017-02-11 15:40:31,335 - DEBUG - Registering agent Clock 105842964073282974559178697588839425728
    # 2017-02-11 15:40:31,335 - DEBUG - Registering agent MailMan 51205723652798966881996459348819854774
    # >>> s.clock.get_clock_speed()
    # 1.0
    # >>> s.time
    # 0
    # >>> s.run(5)
    # 2017-02-11 15:40:41,988 - DEBUG - Pausing Scheduler, use 'run()' to continue. Use 'stop()' to shutdown remote processors.
    # >>> s.time
    # 10.653609275817871  # <--- 10 seconds passed. Not five!
    # >>> s.time
    # 10.653609275817871
    # >>> s.time
    # 10.653609275817871
    # >>> s.run(5)
    # 2017-02-11 15:41:27,403 - DEBUG - Pausing Scheduler, use 'run()' to continue. Use 'stop()' to shutdown remote processors.
    # >>> s.time
    # 10.654609203338623  # <--- Time did not progress.
    # >>> s.time
    # 10.654609203338623  # <--- Time is still not progressing.
    #
    # Wanted behaviour:
    # The clock is set using the api calls to the clock:
    #
    # >>> s = Scheduler()
    # 2017-02-11 15:15:00,197 - INFO - Scheduler is running with uuid: 206586991924651126011034509456004484857
    # 2017-02-11 15:15:00,197 - DEBUG - Registering agent Clock 237028863335333747268219642853960174161
    # 2017-02-11 15:15:00,197 - DEBUG - Registering agent MailMan 108593288939288121173991719827939198422
    # >>> s.time
    # 0
    # >>> s.clock.set_time(1000)
    # >>> s.time
    # 1000
    # >>> s.run(seconds=5)
    # 2017-02-11 15:16:49,395 - DEBUG - Pausing Scheduler, use 'run()' to continue. Use 'stop()' to shutdown remote processors.
    # >>> s.time
    # 1005
    # >>> s.clock.set_clock_speed(200)
    # >>> s.time
    # 1005
    # >>> s.run(seconds=5)
    # 2017-02-11 15:17:41,355 - DEBUG - Pausing Scheduler, use 'run()' to continue. Use 'stop()' to shutdown remote processors.
    # >>> s.time
    # 2005
    # >>> s.time
    # 2005

    ...

    """
    if SKIP_CLOCK_TESTS:
        return
    s = Scheduler(clock_speed=1.0000)
    time_0 = s.time
    clock_speed_0 = s.clock.clock_speed
    assert int(clock_speed_0) == 1.0000, "clock speed is {} and not 1.0000".format(
        clock_speed_0
    )
    new_time = 1000
    s.clock.time = new_time
    clock_time = s.clock.time
    assert (
        clock_time == new_time
    ), "the time should be {} but hasn't been set, as it is {}".format(
        new_time, clock_time
    )
    time_1 = s.time  # the scheduler hasn't run, so it hasn't updated.
    assert (
        time_0 == time_1
    ), "when the scheduler isn't running, time shouldn't progress."
    assert (
        time_0 != clock_time
    ), "when the scheduler isn't running, time shouldn't progress."

    s.run(iterations=5)  # Need to prime the scheduler.
    scheduler_start_time = s.time
    wall_clock_start_time = time.time()

    runtime_iterations = 5
    run_time = 1  # second
    sleep_time = 1  # second
    for i in range(runtime_iterations):
        assert s.time == s.clock.time, "scheduler and schedulers clock are out of sync"
        s.run(seconds=run_time)
        time.sleep(
            sleep_time
        )  # we add the sleep so that if the clock doesn't sleep when the scheduler isn't
        # runing, it will reveal that 10 seconds have passed (total time) and not 5.
        print(".", flush=True, end="")

    wall_clock_end_time = time.time()
    scheduler_end_time = s.time

    dt_wall = wall_clock_end_time - wall_clock_start_time
    dt_scheduler = scheduler_end_time - scheduler_start_time

    if round(wall_clock_end_time - wall_clock_start_time) / 2 == runtime_iterations * 2:
        raise Exception(
            "Schedulers clock did not sleep whilst scheduler wasn't running."
        )

    timing_checks = [
        round(dt_scheduler) - run_time * runtime_iterations == 0,
        round(dt_wall) == runtime_iterations * (run_time + sleep_time),
    ]
    assert all(timing_checks), "The timing checks didn't pass: {}".format(timing_checks)
    s.stop()


def doall():
    global SKIP_CLOCK_TESTS

    SKIP_CLOCK_TESTS = False

    cnt = 0  # counter of tests.
    for k, v in sorted(globals().items()):
        if "test" in k and callable(v):
            v()
            cnt += 1
            print("{} done".format(k))
    print("Ran {} tests with success.".format(cnt))


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.info("Started")
    doall()
    logging.info("Finished")
