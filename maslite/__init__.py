import time
import logging
from copy import deepcopy
from collections import deque
from itertools import count

CRITICAL = logging.CRITICAL
FATAL = CRITICAL
ERROR = logging.ERROR
WARNING = logging.WARNING
WARN = WARNING
INFO = logging.INFO
DEBUG = logging.DEBUG
NOTSET = logging.NOTSET

LOG_LEVEL = logging.DEBUG


class MasLiteException(Exception):
    pass


uuid_counter = count(1)


class AgentMessage(object):
    """
    BaseMessage checks whether the sender and receiver are
    WorldBaseObjects and automatically retrieves their ids.
    If the receiver is None, the message is considered a broadcast
    where the mailman needs to figure out who is subscribing and
    how to get it to the subscribers.
    """

    def __init__(self, sender, receiver=None, topic=None):
        """
        :param sender: The agent (class Agent) or agent-uuid of the sender
        :param receiver: None (broadcast) or The agent (class Agent) or agent-uuid of the receiver
        :param topic: The topic; default is self.__class__.__name__ of the message subclass
        """
        self._sender = None
        self.sender = sender  # sender must be an agent, as a response otherwise can't be returned.
        self._receiver = None
        self.receiver = receiver  # the uuid of the receiving agent.
        if topic is None:
            topic = self.__class__.__name__
        self._topic = topic  # the keyword that the receiver should react upon.
        self._uuid = next(uuid_counter)

    def __str__(self):
        return "From -> To : {} -> {} Topic: {}".format(self.sender, self.receiver, self.topic)

    @property
    def sender(self):
        return self._sender

    @sender.setter
    def sender(self, sender):
        """
        :param sender: the sender (FROM)
        :return:
        """
        if isinstance(sender, Agent):
            self._sender = sender.uuid
        elif sender is None:
            self._sender = None
        else:
            self._sender = sender

    @property
    def receiver(self):
        return self._receiver

    @receiver.setter
    def receiver(self, receiver):
        """
                :param receiver: the intended receiver of the message. Typically the sending
                 agents uuid, retrievable as agent.get_uuid().
                 if the receiver is None, the message is treated as a broadcast to all subscribers
                 of the topic. If there are no subscribers of that topic, the mailman will drop
                 the message.
                :return:
                """
        if isinstance(receiver, Agent):
            self._receiver = receiver.uuid
        elif receiver is None:
            # If receiver is None, the message is treated as a
            # broadcast to all subscribers of the topic.
            # NB. If there are no subscribers of that topic, the mailman
            # will drop the message...
            self._receiver = None
        else:
            self._receiver = receiver

    def copy(self):
        """
        :return: deep copy of the object.
        """
        return deepcopy(self)

    @property
    def topic(self):
        """
        :return: The topic of the message. Typically the saame as Message.__class__.__name__
        """
        return self._topic

    @topic.setter
    def topic(self, topic):
        self._topic = topic

    @property
    def uuid(self):
        """
        :return: returns the UUID of the message.
        """
        return self._uuid

    @uuid.setter
    def uuid(self, value):
        raise ValueError("UUID is permanent throughout the messages' lifetime and cannot be set after instantiation.")


class SubscribeMessage(AgentMessage):
    """ A message class used to subscribe to messages. Used by all agents during `setup` to
     assure that they can receive messages based on their UUID and their class type"""

    def __init__(self, sender, subscription_topic, receiver=None):
        assert isinstance(subscription_topic, (int, float, str)), "A subscription topic must be int, float or str."
        super().__init__(sender=sender, receiver=receiver, topic=self.__class__.__name__)
        self.subscription_topic = subscription_topic


class UnSubscribeMessage(AgentMessage):
    """ A message class used to unsubscribe from messages. Used by all agents during `teardown` to
     assure that they unsubscribe to from all mailing lists."""

    def __init__(self, sender, subscription_topic=None, receiver=None):
        """
        :param sender: the Agent.
        :param subscription_topic: the topic that's nolonger subscribed.
        If `None` then all topics are unsubscribed from.
        :param receiver: None required.
        """
        if subscription_topic is not None:
            assert isinstance(subscription_topic, (int, float, str)), "A subscription topic must be int, float or str."
        super().__init__(sender=sender, receiver=receiver, topic=self.__class__.__name__)
        self.subscription_topic = subscription_topic


class StartMessage(AgentMessage):
    """ A message class that can be used to start stopped agents. The usage must
    be implemented in the Agent subclass as there are no default behaviours."""

    def __init__(self, sender, receiver=None):
        super().__init__(sender=sender, receiver=receiver, topic=self.__class__.__name__)


class PauseMessage(AgentMessage):
    """ A message class used to pause running agents."""

    def __init__(self, sender, receiver=None):
        super().__init__(sender=sender, receiver=receiver, topic=self.__class__.__name__)


class StopMessage(AgentMessage):
    """ A message class that can be used to stop running agents. The usage must
        be implemented in the Agent subclass as there are no default behaviours."""

    def __init__(self, sender, receiver):
        super().__init__(sender=sender, receiver=receiver, topic=self.__class__.__name__)


class SetTimeAndClockSpeedMessage(AgentMessage):
    """
    Message used to set the time on the clock after start.
    """

    def __init__(self, sender, receiver=None, new_time='', new_clock_speed=''):
        """
        :param sender: Sender's uuid
        :param receiver: Reciever's uuid, or if set to None: all subscribers of this message type.
        :param new_time: world_time as time in seconds since 1970-01-01T00:00:00.000000
        :param new_clock_speed: value int, float or None. `None` means non-linear time jumps.
        Time elapses twice as fast as realtime, with a value of 2.0.
        Time elapses ten times slower than realtime with a value of 0.1
        """
        if receiver is None:
            receiver = Clock.__name__
        if isinstance(new_clock_speed, (int, float)):
            if new_clock_speed <= 0:
                raise ValueError("clock speed can't be 0 or less. Use clock_speed=None for that.")
            else:
                pass
        else:
            pass
        super().__init__(sender=sender, receiver=receiver, topic=self.__class__.__name__)
        self.new_time = new_time
        self.new_clock_speed = new_clock_speed


class GetSubscribersMessage(AgentMessage):
    """ A message class used to obtain the a list of subscribers."""

    def __init__(self, sender, subscription_topic, receiver=None):
        super().__init__(sender=sender, receiver=receiver, topic=self.__class__.__name__)
        assert str(subscription_topic)
        self.subscription_topic = subscription_topic
        self.subscribers = None


class GetSubscriptionTopicsMessage(AgentMessage):
    """ A message class used to obtain list of topics that can be subscribed to. """

    def __init__(self, sender, receiver, subscription_topics=None):
        super().__init__(sender=sender, receiver=receiver, topic=self.__class__.__name__)
        self.subscription_topics = subscription_topics


class Agent(object):
    """ The default agent class. """
    uuid_counter = count(1)

    def __init__(self, uuid=None):
        """
        :param uuid: None (default). Should only be set for inspection purposes.
        """
        self.inbox = deque()  # when using self.receive() we get the messages from here
        self.outbox = deque()  # here we post messages when using self.send(msg)
        if uuid is None:
            self._uuid = next(Agent.uuid_counter)  # this is our worldwide unique id.
        else:
            try:
                _ = hash(uuid)
            except TypeError:
                raise TypeError("uuid must be hashable.")
            self._uuid = uuid
        self.operations = dict()  # this is the link between msg.topic and agents response.
        self._is_setup = False  # this tells us that the agent is/ is not setup
        self._quit = False  # this tells the scheduler to kill the agent.
        self._time = 0  # the timestamp in the compute cycle.
        self.keep_awake = False  # this prevents the agent from entering sleep mode when there
        # are no new messages.
        self._logger = None  # The logger is added by the scheduler during "add(agent)".

    @property
    def uuid(self):
        """
        :return: Returns the UUID of the agent. This is guaranteed to be volatile and unique.
        No two runs of the same simulation will have agents with the same UUID.

        beginner errors:
        Q: Agent does not have attribute "uuid".
        A: You forgot to run super().__init__() on the Agent class.
        """
        return self._uuid

    @uuid.setter
    def uuid(self, value):
        raise ValueError("UUID cannot be set once the object has been instantiated")

    def __str__(self):
        return "<{}> uuid: {}".format(self.__class__.__name__, self._uuid)

    def __repr__(self):
        return "<{}> uuid: {}".format(self.__class__.__name__, self._uuid)

    def send(self, msg):
        """ The only method for sending messages in the system.
        Message are deliberately NOT asserted for, as it should be possible
        to dispatch all kinds of objects.
        :param msg: any pickleable object.
        :return: None
        """
        assert isinstance(msg, AgentMessage), "sending messages that aren't based on AgentMessage's wont work"
        self.outbox.append(msg)

    @property
    def messages(self):
        """
        :return: Boolean: True if there are messages.
        """
        if len(self.inbox) > 0:
            return True
        else:
            return False

    def receive(self):
        """
        :return: Returns AgentMessage if any.
        """
        if self.messages:
            return self.inbox.popleft()
        else:
            return None

    def setup(self):
        """ Users can implement this setup method for starting up the kernel agent.

        NB! This method runs automatically when the agent is added to the scheduler !

        Cascades of setups are possible using the message AddNewAgent, such as for example:

            class Minion(Agent):
                def __init__(minion_id):
                    ...


            for minion in range(minions):
                m = Minion(minion_id=minion)
                msg = AddNewAgent(sender=self, agent=m)
                self.send(msg)

        A good approach is to use have functions for each message and register the
        functions in the Agent's class' operations at setup:

            def setup(self):
                self.subscribe(self.uuid)

                self.operations.update({"new request": self.new_request,
                                        "hello": self.receive_hello_msg})

                for topic in self.operations:
                    self.subscribe(topic)
        """
        raise NotImplementedError("derived classes must implement a setup method")

    def teardown(self):
        """Users can implement this teardown method for shutting down the kernel agent.

        ! Runs automatically when the agent is removed from the scheduler !

        """
        raise NotImplementedError("derived classes must implement a update method")

    def update(self):
        """ Users must implement the update method using:
            send(msg)
            receive(msg)
        examples of CnC signals are the classes `StartMessage` and `StopMessage`

        A good approach is to use:

        while self.messages:
            msg = self.receive()
            operation = self.operations.get(msg.topic)
            if operation is not None:
                operation(msg)
            else:
                self.logger("%s %s: don't know what to do with: %s" %
                            (self.__class__.__name__, str(self.uuid())[-6:], str(msg)),
                            log_level="DEBUG")

        if some messages take precedence over others (priority messages), the
        inbox should be emptied in the beginning of the update function for
        sorting. For example:

        priority_topics = [1,2,3]
        priority_messages = deque()  # from collections import deque
        normal_messages = deque()
        while self.messages:
            msg = self.receive()
            if msg.topic in priority_topics:
                priority_messages.append(msg)
            else:
                normal_messages.append(msg)
        priority_messages.extend(normal_messages)
        while len(priority_messages) > 0:
            msg = priority_messages.popleft()
        """
        raise NotImplementedError("derived classes must implement a update method")

    def run(self):
        """ The main operation of the Agent. """
        if not self._quit:
            self.update()

    def is_setup(self):
        """ A function used to check if the agent is setup."""
        return self._is_setup

    def log(self, msg, level=NOTSET):
        """

        :param msg: str or AgentMessage
        :param level: int
        :return:
        """
        if isinstance(msg, AgentMessage):
            msg = str(msg)
        assert isinstance(msg, str)
        try:
            self._logger.log(level=level, msg=msg)
        except Exception:
            # logger not instantiated by Scheduler
            print("logging not set: log message:", level, msg)

    @property
    def time(self):
        """ Returns the time in the simulation. This `time` is posted on the agent when
        it is update by the scheduler. In common usage this should be offset from realtime
        by less than 1 ms. Not that time doesn't progress whilst the agent is being updated.
        Any subclass' need for chronology should use an internal counter."""
        return self._time

    @time.setter
    def time(self, new_time):
        self._time = new_time

    def set_timed_alarm(self, alarm_time, alarm_message=None, relative=False):
        """ A method to be used by the agent to set (and later receive) an alarm message.

        :param alarm_time: int, float: The time (from `self.now()` ) where the agent should
         receive the alarm message.
        :param alarm_message: AgentMessage that the agent should receive.
        :param relative: bool:
            True: alarm goes off at self.time + alarm_time
            False: alarm goes off at alarm_time == self.time
        """
        if relative:
            alarm_time = self.time + alarm_time

        if alarm_message:
            assert isinstance(alarm_message, AgentMessage), "wake up message must be a subclass of agent message"
        assert isinstance(alarm_time, (int, float)), "wake up time must be int or float. Not {}".format(
            type(alarm_time))
        msg = AlarmMessage(sender=self, alarm_time=alarm_time, alarm_message=alarm_message)
        self.send(msg)

    def subscribe(self, topic):
        """
        A method to be used by the agent to set and subscribe to a particular topic
        :param topic: string

        Examples:

        To subscribe to messages for the agent itself, use [1]:
        topic=self.uuid

        To subscribe to messages for the agents own class (including class broadcasts), use [1]:
        topic=self.__class__.__name__

        To subscribe to messages of a particular subject, use:
        topic=AgentMessage.__class__.__name__

        [1] This option is loaded automatically at setup time.

        """
        msg = SubscribeMessage(sender=self, subscription_topic=topic)
        self.send(msg=msg)

    def unsubscribe(self, topic=None):
        """ A method to be used by the agent to unset and unsubscribe to a particular topic
        :param topic: string or None. If None, the agent unsubscribes from everything.

        Note that all agents automatically unsubscribe at teardown.
        """
        msg = UnSubscribeMessage(sender=self, subscription_topic=topic)
        self.send(msg=msg)


class Clock(Agent):
    """The clock is a basic time-keeping object that updates all agents prior to
    running agent.update() """

    def __init__(self, world_time=0, clock_speed=1.00000):
        """
        :param: world_time: int, float: time as seconds since 1970-01-01T00:00:00.000000
        :param: clock_speed: int, float or None: (optional) the clock speed relative to real-time.
        If the clock_speed is set to None, time will jump forward as fast as possible. Use
        this option to run the simulation as fast as possible.
        """
        assert isinstance(world_time, (int, float)), "world_time must be int or float, not: {}".format(type(world_time))
        assert isinstance(clock_speed,
                          (int, float, type(None))), "clock_speed must be int, float or None. Not: {}".format(
            type(clock_speed))
        super().__init__(uuid=-2)
        self._paused = True
        self._time_when_paused = world_time
        self.clock_time = 0.0
        self.offset = 0.0
        self.time = world_time
        self._clock_speed = clock_speed
        self.alarms = []
        self.clock_frequency_measurements = deque(maxlen=5)
        self.operations.update({SetTimeAndClockSpeedMessage.__name__: self.set_time_using_msg,
                                AlarmMessage.__name__: self.set_alarm})
        self._last_timestamp = self.time

    def setup(self):
        self._is_setup = True
        self.subscribe(SetTimeAndClockSpeedMessage.__name__)

    def teardown(self):
        self._is_setup = False
        self.unsubscribe()

    def update(self):
        if self._paused:
            self._resume_after_pause()
        self.tick()  # moving clock's timestamp one "tick" further.
        while self.messages:
            msg = self.receive()
            operation = self.operations.get(msg.topic)
            if operation is not None:
                operation(msg)
        self.check_alarm_clock()  # finally, check the alarm clock.

    # functions that react on messages
    def set_time_using_msg(self, msg):
        assert isinstance(msg, SetTimeAndClockSpeedMessage)
        if isinstance(msg.new_time, (int, float)):
            self.time = msg.new_time
        else:
            pass  # we ignore the '' that the default message contains.
        if isinstance(msg.new_clock_speed, (int, float, type(None))):
            self.clock_speed = msg.new_clock_speed
        else:
            pass  # we ignore the '' that the default message contains.

    @property
    def time(self):
        """
        method equivalent to time.time()
        :returns time, as floating point seconds since 1970-01-01T00:00:00.000000
        """
        if self.clock_speed is None:
            right_now = self._time
        elif self._paused:
            right_now = max(self._time, self._time_when_paused)
        else:
            right_now = (time.time() + self.offset) * self.clock_speed
        self._time = right_now
        return right_now

    @time.setter
    def time(self, world_time):
        """
        :parameter world_time:  time in seconds since simulation start.

        To use real-time offset the simulation with, for example:
        In[2]: import time
        In[3]: time.time()
        Out[3]: 1480074793.2779272
        In[4]: clock.set_time(time.time())
        """
        if not isinstance(world_time, (int, float)):
            raise AttributeError("Cannot set time using unless world_time is provided \
                    as time in seconds since 1970-01-01T00:00:00.000000")
        self.offset = world_time - time.time()
        self._time = world_time

    @property
    def clock_speed(self):
        return self._clock_speed

    @clock_speed.setter
    def clock_speed(self, new_clock_speed):
        """sets the clock speed relative to real-time.
        :param: int, float or None.
        Time elapses twice as fast as real time, with a value of 2.0.
        Time elapses ten times slower than real time with a value of 0.1
        If clock_speed == None, the simulated time will be set by either:
        a. The active messages being exchanged. The clock doesn't tick whilst
           negotiations are ongoing.
        b. The alarm calls booked by the agents: If there are no negotiations,
           time will jump to the next alarm, as this will set off another chain
           of messages.
        """
        if new_clock_speed is None:
            self._clock_speed = None
            return
        if isinstance(new_clock_speed, (int, float)):
            self._clock_speed = new_clock_speed
            return
        raise ValueError("new clock speed must be integer or float, not {}".format(type(new_clock_speed)))

    def tick(self):
        """
        Ticks the clock one 'tick' further. This is disabled if the clock_speed is None,
        as the next timestep then is the next alarm.
        """
        if self.clock_speed is None:
            return

        self._last_timestamp = right_now = self.time
        dt = abs(max(self._last_timestamp, self._time) - right_now)  # uses max in case time has been set.
        self.clock_frequency_measurements.append(dt)

    def set_alarm_clock(self, alarm_time, alarm_message=None):
        """ This function overrides the Agent-class's set_alarm_clock function
        as the Clock-class's sends it to itself, rather than sending it onwards.
        :param alarm_time: time in seconds
        :param alarm_message: message to be sent at alarm time.
        :return: None
        """
        assert isinstance(alarm_time, (int, float)), "alarm_time must be int or float, not: {}".format(type(alarm_time))
        assert isinstance(alarm_message,
                          (type(None), AgentMessage)), "alarm_message must be None or instance of AgentMessage"
        msg = AlarmMessage(sender=self, alarm_time=alarm_time, alarm_message=alarm_message)
        self.set_alarm(msg)

    def set_alarm(self, msg):
        """ Allows the Clock to recieve a message and set an alarm.
        :param msg: AlarmMessage
        """
        assert isinstance(msg, AlarmMessage)
        self.alarms.append((msg.wake_up_time, msg.uuid, msg))
        # The method above uses the decorate-sort-method, using time and uuids.
        self.alarms.sort()

    def check_alarm_clock(self):
        """
        Method get_alarms uses the clock signal latency to assure that a
        wake-up call will not be missed. If the intervals by which the
        :return: list of WakeUpMessages
        """
        if not self.alarms:
            return

        if self.clock_speed is None:
            right_now = self.time
        else:
            right_now = self.time + 1 / self.clock_frequency

        while self.alarms:
            wake_up_time, uuid, msg = self.alarms[0]
            if wake_up_time <= right_now:
                self.send(msg.wake_up_message)
                self.alarms.pop(0)
            else:  # wake_up_time > right now
                break  # then the first alarm is in the future and there
                # is no reason to look any further as the alarms are sorted.

    @property
    def clock_frequency(self):
        """ A method for determining how many times the clock is checked
        per second. This is used by the alarm to assure that the alarm
        doesn't sleep past the wake-up-time.
        :returns: the clock check frequency.
        """
        if len(self.clock_frequency_measurements) == 0:
            cfm = -1  # Clock Frequency Measurements (cfm)
        else:
            cfm = sum(self.clock_frequency_measurements) / len(self.clock_frequency_measurements)
        if cfm <= 0:
            cfm = 10 ** -9
        return 1 / cfm

    @clock_frequency.setter
    def clock_frequency(self, value):
        raise ValueError("You can't set the clock_frequency, but you can set the clock_speed")

    def advance_time_to_next_timed_event(self, issue_stop_message_if_no_more_events=False):
        """
        :param issue_stop_message_if_no_more_events: boolean

        Configures the clock, to jump in time, if no more messages are exchanged
        between agents.
        """
        if self.alarms:
            wake_up_time, uuid, msg = self.alarms[0]
            self.time = wake_up_time
        else:
            if issue_stop_message_if_no_more_events:
                self.log("Scheduler requested clock to advance to next event,\nbut there are no more events.")
                self.send(PauseMessage(sender=self, receiver=Scheduler.__name__))

    def pause(self):
        """ A method used by the scheduler, to pause the clock """
        self._paused = True
        self._time_when_paused = self.time

    def _resume_after_pause(self):
        """ A method used by the clock to reset the offset in time,
        when resuming after being paused. """
        self._paused = False
        self.time = max(self._time, self._time_when_paused)

    def is_waiting_for_the_alarm_clock(self):
        """
        :return: True if the clock only is waiting for alarms to trigger
        """
        if self.alarms:
            if not self.messages:
                return True
        return False

    def is_idle(self):
        """
        :return: True if idle, else False.
        """
        if self.alarms:
            return False
        if self.messages:
            return False
        return True


class AlarmMessage(AgentMessage):
    """Message sent from the AlarmClock to the receiver that needs to wake up.
    :param: wake_up_time (optional) the time in seconds by which the wake
    message should be posted.
    :param: wake_up_event (optional) signal to tell the receiver why it is
    supposed to wake up. This can for example be another Message.
    """

    def __init__(self, sender, receiver=Clock.__name__, alarm_time=0, alarm_message=None):
        super().__init__(sender=sender, receiver=receiver, topic=self.__class__.__name__)
        assert isinstance(alarm_time, (int, float))
        self.wake_up_time = alarm_time
        if alarm_message:
            assert isinstance(alarm_message, AgentMessage)
            if alarm_message.receiver is None:
                alarm_message.receiver = sender
        else:
            alarm_message = AgentMessage(sender=sender, receiver=sender)
        self.wake_up_message = alarm_message


class SchedulerException(MasLiteException):
    pass


class Scheduler(Agent):
    """ The scheduler that handles updates of all agents."""

    def __init__(self, clock_speed=None, pause_if_idle=True,
                 minimum_operating_frequency=1000, logger=None):
        """
        :param: clock_speed: None, float or int: the simulation clock speed.
        :param: pause_if_idle: Boolean.
        :param: minimum_operating_frequency: Sets off an alarm if the ability to update all
        agents drops below the required operating frequency.
        """
        super().__init__(uuid=-1)  # init's self.inbox as a collections.deque() for various purposes
        assert isinstance(self.inbox, deque), "Scheduler can't work without a deque."
        assert isinstance(pause_if_idle, bool)
        assert isinstance(minimum_operating_frequency, (float, int))

        self.mail_queue = deque()
        self.mailing_lists = {}
        self.agents = dict()
        self.needs_update = set()
        self.has_keep_awake = set()
        # The setup will be finalized in `setup`.
        self.clock = Clock(clock_speed=clock_speed)

        self.iterations_to_halt = None
        self.message_count = deque(maxlen=3)  # used to count the number of agent
        # messages seen in an update cycle, so that the scheduler can sleep if
        # none of the agents are active.

        self.pause = False
        self.pause_if_idle = pause_if_idle

        self.operating_frequency = minimum_operating_frequency  # used to throttle
        # the sleep function if there is nothing to do.

        self.operations.update({PauseMessage.__name__: self.pause_msg,
                                StopMessage.__name__: self.stop,
                                AddNewAgent.__name__: self.add_agent_from_message,
                                RemoveAgent.__name__: self.remove_agent_from_message,
                                SubscribeMessage.__name__: self.process_subscribe_message,
                                UnSubscribeMessage.__name__: self.process_unsubscribe_message,
                                GetSubscriptionTopicsMessage.__name__: self.get_subscription_topics,
                                GetSubscribersMessage.__name__: self.get_subscriber_list
                                })

        if logger is None:
            self._logger = logging.getLogger(self.__class__.__name__)
            self._logger.setLevel(LOG_LEVEL)
            self._logger.propagate = False
            if not any(isinstance(h, logging.StreamHandler) for h in self._logger.handlers):
                handler = logging.StreamHandler()
                handler.setLevel(LOG_LEVEL)
                self._logger.addHandler(handler)
            self.log(level=DEBUG, msg="Scheduler is running with uuid: {}".format(self.uuid))
        else:
            self._logger = logger

    def add(self, agent):
        """ Adds an agent to the scheduler
        :param agent: Agent
        """
        assert isinstance(agent, Agent)
        self.log(level=DEBUG, msg="Registering agent {} {}".format(agent.__class__.__name__, agent.uuid))
        if agent.uuid in self.agents:
            raise SchedulerException("Agent uuid already in usage.")
        self.agents[agent.uuid] = agent
        # give agent a child logger with name structure "Scheduler.AgentClass"
        agent._logger = self._logger
        if not agent.is_setup():
            self.process_subscribe_message(SubscribeMessage(agent, agent.uuid))
            self.process_subscribe_message(SubscribeMessage(agent, agent.__class__.__name__))
            agent.setup()
            agent._is_setup = True
        if agent.keep_awake:
            self.has_keep_awake.add(agent.uuid)
        self.needs_update.add(agent.uuid)

    def remove(self, agent_or_uuid):
        """ Removes an agent from the scheduler
        :param agent_or_uuid: Agent
        """
        if not isinstance(agent_or_uuid, Agent):
            agent = self.agents.get(agent_or_uuid, None)
            if agent is None:
                raise ValueError("Agent not found: {}".format(agent_or_uuid))
        else:
            agent = agent_or_uuid
        assert isinstance(agent, Agent)
        if agent is self.clock:
            raise ValueError("Removing the clock is not permitted.")
        if agent.uuid not in self.agents:
            self.log(level=DEBUG, msg="Agent exists but hasn't been added: {}".format(agent_or_uuid))
            return

        self.log(level=DEBUG, msg="DeRegistering agent {}".format(agent.uuid))
        if agent.is_setup():
            self._is_setup = False
            agent.teardown()
            self.send_and_receive(agent)  # empty the agents outgoing messages.
            self.unsubscribe_agent_everywhere(UnSubscribeMessage(sender=agent))
        if agent.uuid in self.needs_update:
            self.needs_update.remove(agent.uuid)
        if agent.uuid in self.has_keep_awake:
            self.has_keep_awake.remove(agent.uuid)
        del self.agents[agent.uuid]

    def setup(self):
        """
        Assures that all agents added to the scheduler prior to
        first `run` are setup, but does not allow mail exchange
        outside the `run` cycle.
        """
        if not self._is_setup:
            self._is_setup = True
            self.process_subscribe_message(SubscribeMessage(sender=self, subscription_topic=self.uuid))
            self.process_subscribe_message(SubscribeMessage(sender=self, subscription_topic=self.__class__.__name__))
            for msgtype in self.operations.keys():
                self.process_subscribe_message(SubscribeMessage(self, msgtype))
            self.send_and_receive(self)
            self.add(self.clock)
            self.update_all_agents()
            self.process_mail_queue()

    def teardown(self):
        """ performs single threaded teardown."""
        for agent in self.agents.values():
            try:
                assert isinstance(agent, Agent)
                if agent.is_setup():
                    agent.teardown()
                    self.send_and_receive(agent)
            except NotImplementedError:
                pass
        self._is_setup = False
        self.log(level=DEBUG, msg="Teardown completed")

    def set_time(self, new_time):
        self.clock.set_time_using_msg(SetTimeAndClockSpeedMessage(sender=self, new_time=new_time))

    def set_new_clock_speed_as_timed_event(self, start_time, clock_speed=None):
        """ set_new_clock_speed_as_timed_event continues the simulation with a new runspeed.
        :param start_time: time in seconds from start where the new clock speed should apply.
        :param clock_speed: integer, float or None. None executes as fast as possible.

        Examples are:
        1. run at maximum speed.
        self.set_new_clock_speed_as_timed_event(start_time=now(), speed=None)

        2. set clock to 10x speed 1 hour into the simulation.
        set_runtime(start_time=now()+1*60*60, speed=10)
        (NB!): This will take 6 minutes in real-time.

        3. set the clock to 1x (real-time) speed 3 hours into the simulation.
        set_runtime(start_time=now()+3*60*60, speed=1)
        (NB!): This will take 1 hour in real time.

        4. set clock to 10x speed 4 hour into the simulation.
        set_runtime(start_time=now()+4*60*60, speed=10)

        5. set the clock to 'None' to run as fast as possible for the rest of the simulation
        set_runtime(start_time=now()+6*60*60, speed=None)
        """
        assert start_time >= 0, "setting a new runspeed in the past doesn't make an sense"
        stm = SetTimeAndClockSpeedMessage(sender=self, new_clock_speed=clock_speed)
        trigger_msg = AlarmMessage(sender=self, alarm_time=self.clock.time + start_time, alarm_message=stm)
        self.clock.inbox.append(trigger_msg)

    def set_pause_time(self, pause_time):
        """ set_pause_time pauses the simulation. To continue un-disrupted use 'run' after pause.
        :param pause_time: time in seconds after start.

        Example: self.set_pause_time(pause_time=now()+15*60*60)
        """
        assert pause_time > 0, "pausing before start time doesn't make any sense"
        pausemsg = PauseMessage(sender=self, receiver=self)
        trigger_msg = AlarmMessage(sender=self, alarm_time=self.clock.time + pause_time, alarm_message=pausemsg)
        self.clock.inbox.append(trigger_msg)

    def set_stop_time(self, stop_time):
        """ set stop time stops the simulation including executing teardown on all agents.
        :param stop_time: time in seconds after start.

        Example: self.set_end_time(end_time=self.now()+24*60*60)

        (NB!): Don't have multiple 'end_time's as the first occurrence of will
        shutdown the simulation.
        """
        assert stop_time > 0, "stopping before start time doesn't make any sense."
        stopMsg = StopMessage(sender=self, receiver=self)
        trigger_msg = AlarmMessage(sender=self, alarm_time=self.clock.time + stop_time, alarm_message=stopMsg)
        self.clock.inbox.append(trigger_msg)

    def run(self, seconds='', iterations='', pause_if_idle='', clock_speed=''):
        """ The main 'run' operation of the Scheduler.

        :param seconds: float, int, None: optional number of real-time seconds to run.
        :param iterations: float, int, None: feature to let the scheduler run for
        N (`iterations`) updates before pausing.
        :param pause_if_idle: boolean: default=False: If no new messages are exchanged
        the scheduler's clock will tick along as any other real-time system.
        If pause_if_idle is set to True, the scheduler will pause once the message queue
        is idle.
        :param clock_speed: float, int or None: If clock speed is not 1.00000,
        the time elapsed in the simulation will be factored by the clockspeed.
        If clock_speed is set to None, the simulation runs as fast as possible.
        See clock.clock_speed for details.

        If set to an abs(integer) > 0, then the scheduler will
        at most update the abs(turns) number of times before exiting. Using iterations
        (turns) is favoured over attempts to use a timer as run time can differ on
        different machines.

        Depending on which of 'seconds' or 'iterations' occurs first, the simulation
        will be paused.
        """
        if clock_speed != '':
            self.clock.clock_speed = clock_speed

        if seconds != '':
            if isinstance(seconds, (int, float)):
                pause_msg = PauseMessage(sender=self, receiver=self)
                self.set_timed_alarm(alarm_time=seconds, alarm_message=pause_msg, relative=True)

        if iterations != '':
            assert isinstance(iterations, int), "iterations must an integer"
            self.iterations_to_halt = abs(iterations)
        else:
            self.iterations_to_halt = None

        if pause_if_idle in (False, True):
            self.pause_if_idle = pause_if_idle

        if self.pause:  # resetting self.pause if "run" is called.
            self.pause = False

        updated_agents = {agent.uuid for agent in self.agents.values() if
                          isinstance(agent, Agent) and any((agent.inbox, agent.outbox))}
        self.needs_update.update(updated_agents)
        if not self._is_setup:
            self.setup()
        super().run()
        if self.pause:  # pause the clock.
            self.clock.pause()

    def stop(self, msg=None):
        """
        Use this method to stop the simulation.
        """
        self._quit = True
        self.log(level=DEBUG, msg="Scheduler stop signal received.")

    def stop_signal_received(self):
        return self._quit

    def update(self):
        """ Once scheduler.run() is activated, the scheduler will remain in the
        main loop of update(). To stop the scheduler send a StopMessage.
        """
        while not self._quit:  # infinite loop unless the scheduler pauses

            self.update_iterations_to_halt()
            if self.pause:
                return None
            self.update_all_agents()
            self.scheduler_update()
            if self.mail_queue:
                for msg in self.mail_queue:
                    self.log(msg=msg, level=logging.DEBUG)
            self.process_mail_queue()
            self.advance_clock_if_agents_are_idle()
            self.check_pause_if_idle_flag()
            self.micro_sleep_if_idle()

    def update_all_agents(self):
        self.needs_update.update(self.has_keep_awake)  # creates unique list of agents that need to update

        # remove the clock as it must run first anyway.
        self.update_agent(self.clock)

        # next, all other agents can be updated.
        for uuid in self.needs_update:
            agent = self.agents[uuid]
            self.update_agent(agent)
            self.maintain_keep_awake_list(agent)
        self.needs_update.clear()

    def update_agent(self, agent):
        if not agent is self.clock:
            agent.time = self.clock.time
        agent.run()
        self.send_and_receive(agent)

    def maintain_keep_awake_list(self, agent):
        if agent.keep_awake:
            if agent.uuid in self.has_keep_awake:
                pass
            else:
                self.has_keep_awake.add(agent.uuid)
        elif not agent.keep_awake:
            if agent.uuid in self.has_keep_awake:
                self.has_keep_awake.remove(agent.uuid)

    def send_and_receive(self, agent):
        """ Transfers all outgoing messages from the agent to the mailman,
         so that subscriptions, monitoring & direct messages can be resolved.
        :param agent: type Agent
        """
        while agent.outbox:  # Send and receive the agents messages
            self.mail_queue.append(agent.outbox.popleft())

    def update_iterations_to_halt(self):
        if self.iterations_to_halt is not None:
            if self.iterations_to_halt > 0:
                self.iterations_to_halt -= 1
                self.log(level=DEBUG, msg="{} iterations to halt".format(self.iterations_to_halt))
            elif self.iterations_to_halt <= 0:
                self.pause = True
                self.log(level=DEBUG, msg="Pausing Scheduler, use 'run()' to continue.")
                self.pause = True

    def scheduler_update(self):
        """ Performs update on the scheduler itself."""
        self._time = self.clock.time

        while self.messages:  # get agent messages in own inbox:
            msg = self.receive()
            if isinstance(msg, AgentMessage):
                operation = self.operations.get(msg.topic)
                if operation is not None:
                    operation(msg)
            else:
                raise SchedulerException(
                    "Scheduler doesn't know what to do with the message:\n{}".format(msg))  # dumps the package quietly.

        self.send_and_receive(self)  # send own messages:

    def process_mail_queue(self):
        """
        distributes the mail, so that when the scheduler pauses, new users
        can debug the agents starting with their fresh state with new messages.
        """
        message_count_in_cycle = len(self.has_keep_awake)  # if agents.keep_awake == True, we need to keep updating.
        while self.mail_queue:
            msg = self.mail_queue.popleft()
            message_count_in_cycle += 1
            if isinstance(msg, AgentMessage):
                topic = msg.topic
                receiver = msg.receiver
                recipients = set()
                # 1. collect the list of recipients
                if receiver in self.mailing_lists:
                    recipients.update(self.mailing_lists[receiver])
                if topic in self.mailing_lists:  # then it's a tracked topic
                    recipients.update((self.mailing_lists[topic]))
                # 2. distribute the mail.
                if len(recipients) > 0:  # receiver is not in self.mailing_lists, so s/h/it might be moving.
                    self.send_to_recipients(msg=msg, recipients=recipients)
                else:
                    self.log(level=DEBUG, msg="{} is not registered on a mailing list.".format(receiver))
            else:
                self.log(level=WARNING,
                         msg="Discovered a non-AgentMessage in the inbox. The message is dumped.")
        self.message_count.append(message_count_in_cycle)

    def send_to_recipients(self, msg, recipients):
        """ Distributes AgentMessages to all registered recipients.
        :param msg: an instance of AgentMessage
        :param recipients: The registered recipients
        :return: Nont
        """
        for uuid in recipients:  # this loop is necessary as a tracker may be on the reciever.
            if uuid == self.uuid:
                agent = self
            else:
                agent = self.agents[uuid]
                self.needs_update.add(uuid)
            if len(recipients) == 1:
                agent.inbox.append(msg)
            else:
                agent.inbox.append(msg.copy())  # deepcopy is used to prevent that anyone modifies a shared object...

    def micro_sleep_if_idle(self):
        """
        if no new messages have been seen, then sleep for a moment as the
        scheduler is running in real-time and is waiting for some external event.
        """
        if self.clock.clock_speed and sum(self.message_count) == 0:
            time.sleep(1 / self.operating_frequency)

    def check_pause_if_idle_flag(self):
        """ if the mailman and clock are idle, then the scheduler should pause.
        """
        if all([sum(self.message_count) == 0,
                self.clock.is_idle(),
                self.pause_if_idle]):
            self.pause = True

    def advance_clock_if_agents_are_idle(self):
        """
        if the clockspeed is None, but alarms are pending and the mailman is idle,
        then a jump in time is appropriate
        """
        if all((sum(self.message_count) == 0,
                self.clock.is_waiting_for_the_alarm_clock(),
                self.clock.clock_speed is None)):
            self.clock.advance_time_to_next_timed_event(issue_stop_message_if_no_more_events=self.pause_if_idle)

    def process_subscribe_message(self, msg):
        """ subscribe lets the Agent react to SubscribeMessage and adds the subscriber.
        to registered subscribers. Used by default during `_setup` by all agents.
        :param msg: SubScribeMessage
        :return: None

        Notes:
        The method adds agent to subscriber list.
        Any agent may subscribe for the same topic many times (this is managed)
        """
        assert isinstance(msg, SubscribeMessage)
        subscription_topic = msg.subscription_topic
        agent_uuid = msg.sender
        if subscription_topic not in self.mailing_lists:
            self.mailing_lists[subscription_topic] = set()
            self.log(level=DEBUG, msg="%s requesting topics added: %s" % (agent_uuid, subscription_topic))
        if agent_uuid not in self.mailing_lists[subscription_topic]:
            self.mailing_lists[subscription_topic].add(agent_uuid)
            if subscription_topic == agent_uuid:
                self.log(level=DEBUG, msg="%s subscribing to messages for itself." % (msg.sender))
            else:
                self.log(level=DEBUG, msg="%s subscribing to topic: %s" % (agent_uuid, subscription_topic))
        else:
            self.log(level=DEBUG, msg="%s already subscribing to topic: %s" % (agent_uuid, subscription_topic))

    def process_unsubscribe_message(self, msg):
        """ unsubscribes a subscriber from messages. Used by default during `_teardown` by all agents.
        :param msg: UnSubscribeMessage
        :return: None
        """
        assert isinstance(msg, UnSubscribeMessage)
        subscription_topic = msg.subscription_topic
        agent_uuid = msg.sender
        if subscription_topic is None:
            self.unsubscribe_agent_everywhere(msg)

        # remove subscriber from list
        if subscription_topic in self.mailing_lists:
            try:
                self.mailing_lists[subscription_topic].remove(agent_uuid)
            except KeyError:
                self.log(level=DEBUG, msg="%s already removed from topic: %s" % (agent_uuid, subscription_topic))
            if len(self.mailing_lists[subscription_topic]) == 0:
                del self.mailing_lists[subscription_topic]
        else:
            self.log(level=DEBUG, msg="%s isn't subscribing to topic: %s" % (agent_uuid, subscription_topic))

    def get_subscriber_list(self, msg):
        """ Returns the list of subscribers of a particular topic."""
        assert isinstance(msg, GetSubscribersMessage)
        subscription_topic = msg.subscription_topic
        if subscription_topic in self.mailing_lists:
            subscribers = self.mailing_lists[subscription_topic].copy()
        else:
            subscribers = None
        msg.receiver = msg.sender
        msg.sender = self
        msg.subscribers = subscribers
        self.send(msg)

    def get_subscription_topics(self, msg):
        """ Returns the list of subscription topics"""
        assert isinstance(msg, GetSubscriptionTopicsMessage)
        if msg.subscription_topics is None:
            msg.subscription_topics = [t for t in self.mailing_lists.keys()]
        else:
            msg.subscription_topics = [msg.subscription_topics]
        msg.receiver = msg.sender
        msg.sender = self
        self.send(msg)

    def unsubscribe_agent_everywhere(self, msg):
        """ Removes sending agent from all mailing lists.
        :param msg: UnSubscribeMessage with subscription_topic=None
        """
        assert isinstance(msg, UnSubscribeMessage)
        assert msg.sender != self.uuid, "The scheduler can't unsubscribe from everything."
        for topic in [t for t in self.mailing_lists.keys()]:
            if msg.sender in self.mailing_lists[topic]:
                self.mailing_lists[topic].remove(msg.sender)

    def pause_msg(self, msg):
        """
        Pauses update of agents until "start" is received.
        msg: PauseMessage
        """
        assert isinstance(msg, PauseMessage)
        self.pause = True

    def add_agent_from_message(self, msg):
        """ Adds an agent using AddNewAgent message
        :param msg: AddNewAgent
        :return: None
        """
        assert isinstance(msg, AddNewAgent)
        agent = msg.agent
        assert isinstance(agent, Agent)
        self.add(agent)

    def remove_agent_from_message(self, msg):
        """ Removes agent using RemoveAgent Message
        :param msg: RemoveAgent
        :return: None
        """
        assert isinstance(msg, RemoveAgent)
        agent = msg.agent_to_be_removed
        self.remove(agent)


class AddNewAgent(AgentMessage):
    """
    Message class for adding new Agents at runtime.
    """

    def __init__(self, sender, agent, receiver=Scheduler.__name__):
        """
        :param sender: The sender who wants to add the attached agent.
        This field can be used for error messages and authorisation.
        :param agent: The instance of the agent to be added.
        """
        super().__init__(sender=sender, receiver=receiver)
        assert isinstance(agent, Agent)
        self.agent = agent


class RemoveAgent(AgentMessage):
    """
    Message class for removing an Agent at runtime.
    """

    def __init__(self, sender, agent_or_agent_uuid, receiver=Scheduler.__name__):
        """
        :param sender: The sender who wants to add the attached agent.
        This field can be used for error messages and authorisation.
        :param agent_or_agent_uuid: The uuid of the agent to be removed.
        """
        super().__init__(sender=sender, receiver=receiver)
        self.agent_to_be_removed = agent_or_agent_uuid


