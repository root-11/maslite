from outscale.core import Agent, AgentMessage, AlarmMessage, PauseMessage, SetTimeMessage, StartMessage, StopMessage, \
    SubscribeMessage, UnSubscribeMessage, GetSubscribersMessage, GetSubscriptionTopicsMessage, Clock, MailMan, \
    Scheduler, AddNewAgent, RemoveAgent
from outscale_tests.importable_agents_for_tests import WorkIntensiveAgent, TestAgent
from random import randint
import time
import pickle
import logging
LOG_LEVEL = logging.INFO
from uuid import uuid4


def test01():
    """ Test basic object creation including all messages"""
    a = Agent()
    _ = str(a)  # checking that object_printer works for the agent.
    # print(_) # uncomment this line if you want to see the print.
    assert a.keep_awake == False, "the default agent should be asleep"

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

    a = TestAgent()
    assert a.is_setup() == False

    a.receive()  # forcing receive in stupidity and making sure that the exception is caught and handled gracefully.

    print("Basic agent tests done")

    # Essential message functions
    messages = []
    add = messages.append
    basic_msg = AgentMessage(sender=a, receiver=a, topic="test")
    assert basic_msg.get_receiver() == a.get_uuid()
    assert basic_msg.get_sender() == a.get_uuid()
    assert basic_msg.get_topic() == "test"
    assert isinstance(basic_msg.get_uuid(), int)
    assert basic_msg.delivery_attempts == 0
    basic_msg.failed_delivery_attempt()
    assert basic_msg.delivery_attempts == 1

    # use the uuid to set sender.
    basic_msg.set_sender(a.get_uuid())

    # test the update function with a non-specific message
    a.inbox.append(basic_msg)
    a.run()
    a._quit = True
    a.run()

    # All the messages below should be able to create without errors.
    add(basic_msg)
    add(AlarmMessage(sender=a, receiver=a, alarm_time=44, alarm_message=messages[0]))
    add(AlarmMessage(sender=a, receiver=a, alarm_time=50))
    add(PauseMessage(sender=a, receiver=a))
    add(SetTimeMessage(sender=a))
    add(StartMessage(sender=a, receiver=a))
    add(StopMessage(sender=a, receiver=a))
    add(SubscribeMessage(sender=a, receiver=a, subscription_topic="Tests"))
    usm = UnSubscribeMessage(sender=a, receiver=a, subscription_topic="Testing")
    assert usm.get_subscription_topic() == "Testing"
    add(usm)
    add(GetSubscriptionTopicsMessage(sender=a, receiver=a))
    add(GetSubscribersMessage(sender=a, receiver=a, subscription_topic="Testing"))

    for msg in messages:
        _ = str(msg)   # check that object_printer works for every kind of message....!
        # print(_) # uncomment this line if you want to see the messages printed.
    print("Message tests complete")


def test02():  # Clock tests
    test_duration = 5 # seconds
    configurations = [[0, 1], [10,1], [100,1], [1000,1], [0, 2], [10,2], [100,2], [1000,2], [10,10]]
    for set_time, speed in configurations:
        c = Clock(world_time=set_time, clock_speed=speed)
        c.run()
        start = c.now()
        start_time = time.time()
        while time.time() < start_time + test_duration:
            if randint(0,1):
                c.run()
            end = c.now()
        end_time = time.time()
        elapsed_real_time = end_time - start_time
        elapsed_clock_time = (end - start) / speed
        tolerance = abs(elapsed_clock_time - elapsed_real_time)
        if tolerance != 0:
            hz = 1/tolerance
        else:
            hz = 10**6
        values = ["end-time: {}".format(end),
                  "start-time: {}".format(start),
                  "dt: {}".format(end-start),
                  "clock-frq: {}".format((end - start) / speed),
                  "clock-speed: {}".format(speed)]
        logging.log(logging.DEBUG,
                    "clock precision is around {} Hz with config: [{},{}] and values: \n\t{}".format(hz, set_time, speed, "\n\t".join(values)))
        assert hz > 900, "clock frequency was {} Hz".format(hz)
        print(".", end='')

def test02a():
    c = Clock()
    # assert c.now() == 0.0, "launching the Clock shouldn't take 100 msecs'."
    assert isinstance(c.get_clock_frequency(), float)  # check that the function works.
    assert isinstance(c.get_clock_speed(), (int, float))
    assert isinstance(c.get_uuid(), int)
    dummy_msg = AgentMessage(c)
    msg = AlarmMessage(sender=c, receiver=c, alarm_time=1.5, alarm_message=dummy_msg)
    c.set_alarm(msg)
    assert len(c.alarms)==1, "the alam message should be here."
    c.run() # c.run runs both: c.setup(), c.update(), c.teardown()
    start = time.time()
    while dummy_msg not in c.outbox:
        c.run()
    end = time.time()
    assert 1.45 < end-start < 1.55, "The alarm message should be returned within 1.5 secs +/-10%"

    # react's to functions:
    timestamp = time.time()-2  # setting the timestamp in the past to avoid sleeping.

    new_time = -10**9 # setting time to the beginning of the universe.
    set_time_msg = SetTimeMessage(c, c, new_time=new_time)
    c.set_time_using_msg(set_time_msg)
    assert c.now() < -10**8, "Time should have been set back"

    # running the clock at a million times real-time.
    new_clock_speed = 10**6
    set_time_msg = SetTimeMessage(c, c, new_time=c.now(), clock_speed=new_clock_speed)
    c.set_time_using_msg(set_time_msg)
    c.get_clock_speed() == new_clock_speed
    time_measurements = []
    start = c.now()
    for i in range(4):
        time.sleep(1)
        end = c.now()
        time_measurements.append(end-start)  # should be appx. 1 second each, which equals 10**6 seconds.
        start = end
    average = sum(time_measurements)/len(time_measurements)
    tolerance = 0.05
    assert new_clock_speed * (1-tolerance) < average < new_clock_speed * (1+tolerance), "clock speed progressed at {}, whilst {} +/-{}% was expected".format(average,new_clock_speed, 100*tolerance)

    try:
        c.set_time("1970-01-01T00:00:00.000000")
        assert False, "The above usage of a timestring is invalid."
    except AttributeError:
        assert True
    except Exception:
        assert False, "The try/except should have raised an AttributeError."

    try:
        c.set_clock_speed("fast")
    except AttributeError:
        assert True
    except Exception:
        assert False, "Setting clock speed requires an integer or float"

    try:
        msg = SetTimeMessage(sender=44, receiver=c, new_time="now")
    except AttributeError:
        assert True
    except Exception:
        assert False, "The set time message's new_time does not accept a string."

    try:
        msg = SetTimeMessage(sender=44, receiver=c, new_time=time.time(), clock_speed="2x")
    except AttributeError:
        assert True
    except Exception:
        assert False, "The set time message's clock_speed does not accept a string."


    msg = AgentMessage(sender=1, receiver=Clock.__name__, topic="irrelevant topic")
    c.inbox.append(msg)
    try:
        c.update()  # nothing should change.
    except Exception:
        assert False, "the clock should have ignored the message."


def test03():  #  Mailman tests.
    mm = MailMan()
    mm.run()
    assert len(mm.agent_register.keys()) == 1, "The mailman should be able to register itself."
    assert len(mm.mailing_lists.keys()) == 2, "The mailman should have registered itself as a class and uuid"
    assert mm.get_uuid() in mm.mailing_lists.keys(), "the mailman should be registered here."
    assert mm.__class__.__name__ in mm.mailing_lists.keys(), "the mailman's class should be registered here too."
    getsubs = GetSubscribersMessage(sender=mm,
                                    receiver=mm,
                                    subscription_topic=mm.__class__.__name__)
    mm.inbox.append(getsubs)
    mm.run()  # running the getsubs message results in an update getsubs message
    # which will keep looping to the mailman itself as sender and receiver is the mailman.
    assert len(mm.inbox) == 1, "mailman should have received its own GetSubscribersMessage"
    getsubs2 = GetSubscribersMessage(sender=mm,
                                    receiver=None,
                                    subscription_topic=mm.__class__.__name__)
    # The message above assert that handling "None" as receiver also works.
    mm.inbox.append(getsubs2)
    mm.run()
    assert len(mm.inbox) == 2, "mailman should have received its own GetSubscribersMessage"
    assert getsubs2.receiver == mm.get_uuid(), "the receiver of the getsubs2 message should have been updated from None to the mailmans uuid"

    test_framework_msg = "Test framework is sending a faulty message to the mailman"
    # if LOG_LEVEL == logging.DEBUG:
    #     print(test_framework_msg, flush=True)
    # mm.logger.debug(test_framework_msg)
    faulty_msg = "7"
    mm.inbox.append(faulty_msg)
    try:
        mm.run()
        test_framework_msg = "The faulty message above was expected as a part of the testing."
        # if LOG_LEVEL == logging.DEBUG:
        #     print(test_framework_msg, flush=True)
        # mm.logger.debug(test_framework_msg)
    except Exception:
        raise AssertionError("the agent should handle a faulty message gracefully.")

    # clearing inbox from the junk messages above:
    while mm.messages():
        _ = mm.receive()
    while mm.outbox:
        mm.outbox.popleft()

    us_msg = UnSubscribeMessage(sender=mm, subscription_topic="some rubbish that isn't subscribed for")
    mm.inbox.append(us_msg)
    mm.logger("the error message below should say that the subject never was subscribed to", log_level="DEBUG")
    mm.run()

    gstm = GetSubscriptionTopicsMessage(mm,mm)
    mm.inbox.append(gstm)
    mm.run()
    assert len(mm.inbox) == 1, "the mailman should have received its own message"
    response = mm.inbox.pop()
    assert isinstance(response, GetSubscriptionTopicsMessage)
    assert response.get_uuid() == gstm.get_uuid(), "the gstm message should have been updated."
    topics = response.get_subscription_topics()
    assert isinstance(topics, list)

    subscription_topic = "random topic"
    subs_msg = SubscribeMessage(sender=mm, subscription_topic=subscription_topic)
    mm.inbox.append(subs_msg)
    mm.run()

    gstm = GetSubscriptionTopicsMessage(mm,mm)
    mm.inbox.append(gstm)
    mm.run()
    response = mm.inbox.pop()
    assert isinstance(response, GetSubscriptionTopicsMessage)
    assert response.get_uuid() == gstm.get_uuid(), "the gstm message should have been updated."
    assert len(response.get_subscription_topics()) == len(topics) + 1, "the list of topics should now be one topic longer."

    subtop = AgentMessage(sender=mm, receiver=None, topic=subscription_topic)
    mm.inbox.append(subtop)
    mm.run() # mailman should receive the message, but not know what to do with it.

    # clearing inbox from the junk messages above:
    junk_cleared = 0
    while mm.messages():
        _ = mm.receive()
        junk_cleared +=1
    while mm.outbox:
        mm.outbox.popleft()
        junk_cleared +=1
    assert junk_cleared == 0, "Mailman cleared out {} junk messages. Should have been zero as the junk messages are dumped quietly".format(junk_cleared)

    un_subs_msg = UnSubscribeMessage(sender=mm, subscription_topic=subscription_topic)
    mm.inbox.append(un_subs_msg)
    mm.run()

    gstm = GetSubscriptionTopicsMessage(mm,mm)
    mm.inbox.append(gstm)
    mm.run()
    assert len(mm.inbox) == 1, "There is more than one message? Can't be right..."
    response = mm.inbox.pop()
    assert isinstance(response, GetSubscriptionTopicsMessage)
    assert response.get_uuid() == gstm.get_uuid(), "the gstm message should have been updated."
    assert len(response.get_subscription_topics()) == len(topics), "the extra topic should have been removed."

    special_msg = AgentMessage(sender=mm, receiver=7, topic="magic rocket man")  # I'm pretty sure that the mailman doesn't have a function for that topic, nor that sender...
    special_msg2 = special_msg.copy()
    mm.inbox.append(special_msg)
    mm.update()
    # mm.run()
    for i in range(mm.tolerated_redelivery_attempts+1):
        mm.update()
    assert len(mm.inbox) == 0, "Mailman should have dumped the message."
    mm.run()
    assert True, "mm run should finish by itself."


def test04():  # Mailman tests.
    tolerated_redelivery_attempts = 5
    mm = MailMan(tolerated_redelivery_attempts=tolerated_redelivery_attempts)
    mm.run()

    # broadcast test.
    agents = []
    for i in range(3):
        a = TestAgent()
        mm.add(a)
        agents.append(a)
    topic = uuid4().hex  # the perfect random topic generator!
    msg = AgentMessage(sender=mm, receiver=a.__class__.__name__, topic=topic)
    mm.inbox.append(msg)
    mm.run()
    assert len(mm.mailing_lists[a.__class__.__name__]) == 3, "There should be 3 subscribers to 'TestAgent'"
    for agent in agents:
        for msg in agent.inbox:
            assert isinstance(msg, AgentMessage)
            if all([msg.get_sender()==mm.get_uuid(),
                    msg.get_receiver()==a.__class__.__name__,
                    msg.get_topic()==topic]):
                break
        else:
            assert False, "The msg above was sent to the TestAgent class and should have been delivered to the 3 TestAgents"

    # we try to remove an agent the brute way to force a deferred delivery call
    a1 = agents[0]
    assert isinstance(a1, Agent)
    del mm.agent_register[a1.get_uuid()]  # the agent is now gone, but will still
    # exist in the mailinglists.
    topic = uuid4().hex
    msg = AgentMessage(sender=mm, receiver=a.__class__.__name__, topic=topic)
    mm.inbox.append(msg)
    for i in range(tolerated_redelivery_attempts//2):
        mm.update()
        assert len(mm.inbox) == 1, "A deferred delivery should be in the inbox..."
    mm.agent_register[a1.get_uuid()] = a1
    mm.update()
    assert len(mm.inbox) == 0, "The deferred delivery should have been delivered..."
    # assert msg in a1.inbox, "A1 should have received a copy..."

    print("Mailman tests complete")


def test05():  # Single threaded scheduler tests.
    s1 = Scheduler(number_of_multi_processors=0)
    assert s1.clock.now() < 0.2, "launching the Scheduler shouldn't take 200 msecs'."
    start = time.time()
    s1.run(seconds=1)
    end = time.time()
    assert 0.5 < (end - start) < 1.5, "the scheduler should have timedout in ~1 sec. Actual time was {}".format(end-start)
    print("Basic scheduler test complete")
    s1.stop()


def test06():
    """ Testing the mailmans broadcast functionality."""
    s = Scheduler(number_of_multi_processors=0)
    agents = [TestAgent() for i in range(10)]
    for agent in agents:
        s.add(agent)
    agent_topic = agents[0].__class__.__name__
    spam_msg = AgentMessage(sender=s, receiver=None, topic=agent_topic)
    s.mailman.inbox.append(spam_msg)
    print("Mailman's broadcast functionality works...")
    s.run(iterations=5)
    # making a genuine agent message but injecting it into the mailmans subscribe method which will fail.
    mm = s.mailman
    spam_msg = AgentMessage(sender=mm, receiver=mm, topic="subscribe")
    mm.inbox.append(spam_msg)
    s.run(iterations=5)

    # injecting an unsubscribe message for a topic that never was subscribed for.
    fake_unsub_msg = UnSubscribeMessage(sender=s, subscription_topic="black ninjas")
    mm.inbox.append(fake_unsub_msg)
    s.run(iterations=5)

    sub_msg = SubscribeMessage(s, "black ninja's")
    mm.inbox.append(sub_msg)
    s.run(iterations=5)

    topic = "fluffy poppies"
    get_subs_wrong_topic = GetSubscribersMessage(s, topic)
    assert get_subs_wrong_topic.get_subscribers() == None
    mm.inbox.append(get_subs_wrong_topic)
    s.run(iterations=5)

    # testing that remove agent works.
    dead_agent = agents.pop(0)
    s.remove(dead_agent)

    # sticking a dead_agent into the schedulers inbox
    s.inbox.append(dead_agent)
    assert dead_agent in s.agents, "The agent should have been added here!"
    s.run(iterations=1)

    # testing the schedulers teardown.
    s.teardown()
    s.stop()


def test07():  # Multi(processing/threaded) Scheduler tests
    s2 = Scheduler(number_of_multi_processors=0)
    start = time.time()
    s2.run(seconds=3)
    end = time.time()
    assert 2.5 < end - start < 3.5, "the scheduler should have timedout in ~1 sec."
    print("Timeout test for single-processing completed.")
    s2.stop()


def test08():
    # Multi(processing/threaded) Scheduler tests
    s2 = Scheduler(number_of_multi_processors=1)
    start = time.time()
    s2.run(seconds=3)
    end = time.time()
    assert 2.5 < end - start < 3.5, "the scheduler should have timedout in ~1 sec."
    s2.stop()
    print("Timeout test for multiprocessing completed.")


def test09():
    cores = 2
    print("running {} co-processors".format(cores))
    s2 = Scheduler(number_of_multi_processors=cores)
    s2.setup()
    s2.run(seconds=3)
    default_subscribers = len(s2.mailman.mailing_lists.keys())
    print("mailman has registered {} default subcribers".format(default_subscribers))

    can_agent_be_pickled = WorkIntensiveAgent(name=44)
    temp = pickle.dumps(can_agent_be_pickled)
    assert isinstance(temp, bytes), "If agents can't be pickled, they won't fit onto the multiprocessing.queue"

    agent_pool = 10
    print("starting multiprocessing {} agents.".format(agent_pool))
    for i in range(agent_pool):
        a = WorkIntensiveAgent(name=i)
        s2.add(a)
    seconds = agent_pool//2
    s2.run(seconds=seconds)
    assert len(s2.mailman.mailing_lists.keys()) - default_subscribers == agent_pool + 1  # 10 agents + the class.
    print("mailman has registered {} new subscribers".format(len(s2.mailman.mailing_lists.keys())- default_subscribers))
    s2.stop()
    print("Scheduler multiprocessing tests complete")


def test10():
    s2 = Scheduler(number_of_multi_processors=4)
    s2.setup()
    agent_pool = 5
    print("starting multiprocessing {} agents.".format(agent_pool))
    for i in range(agent_pool):
        a = WorkIntensiveAgent(name=i)
        s2.add(a)
    s2.run(seconds=agent_pool//2)
    s2.stop()
    print("Scheduler multiprocessing tests complete")


class WrongLyDesignedAgent(Agent):
    def __init__(self):
        super().__init__()
        self.badlogger = logging.getLogger(self.__class__.__name__)


def test11():
    s = Scheduler()
    assert s.multiprocessing is True, "This test doesn't working with multiprocessing disasbled"

    try:
        bad_agent = WrongLyDesignedAgent()
        s.add(bad_agent)
    except TypeError:
        assert True
    except Exception:
        assert False, "The wrongly designed agent above keeps a io pipe open which cannot be pickled."
    assert True
    s.run(seconds=3)
    s.stop()


def test12():
    """ Test to add/remove agents using messages sent to the scheduler's class name."""
    s = Scheduler(number_of_multi_processors=0)
    a = TestAgent()
    msg = AddNewAgent(sender=s, agent=a)
    s.inbox.append(msg)
    s.run(iterations=3)
    assert a in s.agents, "TestAgent class should be registered by now"
    s.run(iterations=10)
    assert TestAgent.__name__ in s.mailman.mailing_lists.keys(), "TestAgent class should be registered by now"
    msg = RemoveAgent(sender=s, agent_or_agent_uuid=a)
    s.inbox.append(msg)
    s.run(iterations=5)
    assert TestAgent.__name__ not in s.mailman.mailing_lists.keys(), "TestAgent class should be de-registered by now"
    s.stop()


def test13():
    s = Scheduler(number_of_multi_processors=0)
    start = time.time()
    s.run(seconds=1)
    end = time.time()
    assert end-start < 2, "The scheduler was supposed to stop within a second. Apparently it didn't."
    s.stop()


def test14():
    """ set clock_speed to None.
    # set_new_clock_speed_as_timed_event
    # set_pause_time
    # set_stop_time """
    start = time.time()
    s = Scheduler(number_of_multi_processors=0)
    s.clock.set_time(world_time=0)
    s.set_new_clock_speed_as_timed_event(start_time=0, clock_speed=None)
    s.set_pause_time(10)
    s.run()
    assert s.clock.clock_speed is None, "Clock speed doesn't seem to have been set to 'None'...!"
    assert 10 <= s.now() <= 10.01, "Timing problem..!"
    s.set_stop_time(s.now()+100)
    s.run()
    end = time.time()
    assert end-start < 0.1, "The time progressed slower than expected."
    s.stop()


def test15():
    pass # test scheduler.inbox(PauseMessage)


def test16():
    pass # multiprocessor stopMsg


def test17():
    pass  # agent.set_alarm_clock function


def test18():
    """ clock.advance_to_next_event """
    c = Clock(clock_speed=None)
    dt = 2
    now = c.now()
    c.set_alarm_clock(alarm_time=now + dt, alarm_message=AgentMessage(sender=c, receiver=c, topic="hello world"))
    c.advance_time_to_next_timed_event()
    after = c.now()
    assert dt == after - now, "Error: dt was {}, whilst c.now is {} and now was {}".format(dt, after, now)


def test19():
    """ run until idle """
    s = Scheduler(number_of_multi_processors=0, pause_if_no_messages_for_n_iterations=10)
    start = time.time()
    s.run(run_until_no_new_events=True)
    end = time.time()
    assert s.pause, "The scheduler should have paused"
    assert end - start < 1, "took too long."


def test20():
    pass  # mailman delivery error due to multiprocessing


def test21():
    pass  # slow multiprocessor shutdown due to busy agent.


def test22():
    pass  # data persistence / recovery
    # Api: scheduler.save(filename=self.__name__.sqlite)
    # Api: scheduler.load(databasefile=self.__name__.sqlite)


def test23():
    pass  # test usage of logfile.


def test24():
    pass # remove agent based on uuid, not agent.


def test25():
    s = Scheduler(number_of_multi_processors=0)
    a = TestAgent()
    s.add(a)
    an_agent_uuid = a.get_uuid()
    s.remove(an_agent_uuid)
    s.run(iterations=1)
    for a in s.agents:
        if hasattr(a, "get_uuid"):
            if an_agent_uuid == a.get_uuid():
                assert False, "Hmm... This agent should have been removed..."
    s.stop()


def test26():
    # TODO: Add test where scheduler contains another scheduler.
    pass
    s = Scheduler(number_of_multi_processors=0)
    s.run(pause_if_idle=True)

def test27():
    """ Description:
    This test has been added for starting and pausing the scheduler, so that it can be
    assured that time only progresses whilst the scheduler is running!

    Example of bug:
    >>> s= Scheduler(number_of_multi_processors=0)
    2017-02-11 15:40:31,334 - INFO - Scheduler is running with uuid: 33892713549718271865085484516606075993
    2017-02-11 15:40:31,335 - DEBUG - Registering agent Clock 105842964073282974559178697588839425728
    2017-02-11 15:40:31,335 - DEBUG - Registering agent MailMan 51205723652798966881996459348819854774
    >>> s.clock.get_clock_speed()
    1.0
    >>> s.now()
    0
    >>> s.run(5)
    2017-02-11 15:40:41,988 - DEBUG - Pausing Scheduler, use 'run()' to continue. Use 'stop()' to shutdown remote processors.
    >>> s.now()
    10.653609275817871  # <--- 10 seconds passed. Not five!
    >>> s.now()
    10.653609275817871
    >>> s.now()
    10.653609275817871
    >>> s.run(5)
    2017-02-11 15:41:27,403 - DEBUG - Pausing Scheduler, use 'run()' to continue. Use 'stop()' to shutdown remote processors.
    >>> s.now()
    10.654609203338623  # <--- Time did not progress.
    >>> s.now()
    10.654609203338623  # <--- Time is still not progressing.

    Wanted behaviour:
    The clock is set using the api calls to the clock:

    >>> s = Scheduler()
    2017-02-11 15:15:00,197 - INFO - Scheduler is running with uuid: 206586991924651126011034509456004484857
    2017-02-11 15:15:00,197 - DEBUG - Registering agent Clock 237028863335333747268219642853960174161
    2017-02-11 15:15:00,197 - DEBUG - Registering agent MailMan 108593288939288121173991719827939198422
    >>> s.now()
    0
    >>> s.clock.set_time(1000)
    >>> s.now()
    1000
    >>> s.run(seconds=5)
    2017-02-11 15:16:49,395 - DEBUG - Pausing Scheduler, use 'run()' to continue. Use 'stop()' to shutdown remote processors.
    >>> s.now()
    1005
    >>> s.clock.set_clock_speed(200)
    >>> s.now()
    1005
    >>> s.run(seconds=5)
    2017-02-11 15:17:41,355 - DEBUG - Pausing Scheduler, use 'run()' to continue. Use 'stop()' to shutdown remote processors.
    >>> s.now()
    2005
    >>> s.now()
    2005

    ...

    """
    s = Scheduler(number_of_multi_processors=0)
    time_0 = s.now()
    clock_speed_0 = s.clock.get_clock_speed()
    assert int(clock_speed_0) == 1.0000, "clock speed is {} and not 1.0000".format(clock_speed_0)
    new_time = 1000
    s.clock.set_time(new_time)
    clock_time = s.clock.now()
    assert clock_time == new_time, "the time should be {} but hasn't been set, as it is {}".format(new_time, clock_time)
    time_1 = s.now()  # the scheduler hasn't run, so it hasn't updated.
    assert time_0 == time_1, "when the scheduler isn't running, time shouldn't progress."
    assert time_0 != clock_time, "when the scheduler isn't running, time shouldn't progress."

    s.run(iterations=5)  # Need to prime the scheduler.
    scheduler_start_time = s.now()
    clock_start_time = s.clock.now()
    wall_clock_start_time = time.time()
    seconds = 5
    for i in range(seconds):
        logging.log(logging.DEBUG,
                    "iteration: {}, start, scheduler time: {}, clock time: {}".format(i, s.now(), s.clock.now()))
        s.run(seconds=1)
        logging.log(logging.DEBUG,
                    "iteration: {}, end, scheduler time: {}, clock time: {}".format(i, s.now(), s.clock.now()))
        time.sleep(1)  # we add the sleep so that if the clock doesn't sleep when the scheduler isn't
        # runing, it will reveal that 10 seconds have passed (total time) and not 5.
    wall_clock_end_time = time.time()
    clock_end_time = s.clock.now()
    scheduler_end_time = s.now()
    timing_checks = [round(clock_end_time-clock_start_time) - seconds == 0,
                     round(scheduler_end_time-scheduler_start_time) - seconds == 0,
                     round(wall_clock_end_time-wall_clock_start_time) == seconds * 2]
    assert all(timing_checks), "The timing checks didn't pass: {}".format(timing_checks)
    s.stop()




def doall():
    cnt = 0  # counter of tests.
    for k,v in sorted(globals().items()):
        if k.startswith("test") and callable(v):
            v()
            cnt += 1
            print("test {} done".format(k))
    print("Ran {} tests with success.".format(cnt))

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.info('Started')
    doall()
    logging.info('Finished')
