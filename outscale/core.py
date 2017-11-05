import os
import sys
import time
import queue
import pickle
import logging
import multiprocessing
from random import randint
from uuid import uuid4
from copy import deepcopy
from collections import deque


LOG_LEVEL = logging.INFO


class AgentMessage(object):
    """
    BaseMessage checks whether the sender and receiver are
    WorldBaseObjects and automatically retrieves their ids.
    If the receiver is None, the message is considered a broadcast
    where the mailman needs to figure out who is subscribing and
    how to get it to the subscribers.
    """
    def __init__(self, sender, receiver=None, topic=None, tolerated_delivery_attempts=10):
        """
        :param sender: The agent (class Agent) or uuid4.int of the sender 
        :param receiver: None (broadcast) or The agent (class Agent) or uuid4.int of the receiver 
        :param topic: The topic; default is self.__class__.__name__ of the message subclass
        """
        self._sender = None
        self.sender = sender  # sender must be an agent, as a response otherwise can't be returned.
        self._receiver = None
        self.receiver = receiver  # the uuid of the receiving agent.
        if topic is None:
            topic = self.__class__.__name__
        self._topic = topic          # the keyword that the receiver should react upon.
        self._delivery_attempts_left = tolerated_delivery_attempts   # an auto-decrementing value used by the mailman for failed delivery attempts.
        self._uuid = uuid4().int     # this is our worldwide unique id.

    def __str__(self):
        return "<{}>\n\tFrom: {}\n\tTo: {}\n\tTopic: {}\n\tMessage UUID: {}".format(
            self.__class__.__name__, self.sender, self.receiver, self.topic, self.uuid)

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
            receiver_uuid = None
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

    # def get_uuid(self):
    #     """
    #     :return: returns the UUID of the message.
    #     """
    #     return self.uuid

    @property
    def uuid(self):
        """
        :return: returns the UUID of the message.
        """
        return self._uuid

    @uuid.setter
    def uuid(self, value):
        raise ValueError("UUID is permanent throughout the messages' lifetime and cannot be set after instantiation.")

    @property
    def delivery_attempts_left(self):
        return self._delivery_attempts_left

    def failed_delivery_attempt(self):
        """
        Counter used by the mailman to determine when to stop attempts to redeliver the message.
        """
        self._delivery_attempts_left -= 1


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
    def __init__(self, sender, subscription_topic, receiver=None):
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


class LogMessage(AgentMessage):
    """ The default message type used for logging.

    Notes: Logs should not be written by agents directly. This is due to multiprocessing,
    where agents will be able to keep a log handler open. The log messages are therefore
    posted via the messaging system and posted to the logs by the scheduler.
    """
    def __init__(self, sender, receiver, log_level, log_message):
        log_levels = {'CRITICAL', 'ERROR', 'WARN', 'WARNING', 'INFO', 'DEBUG', 'NOTSET'}
        assert log_level in log_levels, "Log_level '{}' not in known log_levels: {}".format(log_level, log_levels)
        super().__init__(sender=sender, receiver=receiver, topic=self.__class__.__name__)
        self.log_level = log_level
        self.log_message = log_message


class SetTimeAndClockSpeedMessage(AgentMessage):
    """
    Message used to set the time on the clock after start.
    """
    def __init__(self, sender, receiver=None, new_time=0, new_clock_speed=1.000000):
        """
        :param sender: Sender's uuid
        :param receiver: Reciever's uuid, or if set to None: all subscribers of this message type.
        :param new_time: world_time as time in seconds since 1970-01-01T00:00:00.000000
        :param new_clock_speed: value int or float
        Time elapses twice as fast as realtime, with a value of 2.0.
        Time elapses ten times slower than realtime with a value of 0.1
        """
        super().__init__(sender=sender, receiver=receiver, topic=self.__class__.__name__)
        if not isinstance(new_time, (float, int)):
            raise AttributeError("Cannot set time using {}. Use int or float.".format(new_time))
        if not isinstance(new_clock_speed, (float, int, type(None))):
            raise AttributeError("Cannot set clock speed using {}. Use int or float or None.".format(new_clock_speed))
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


class DeferredDeliveryMessage(AgentMessage):
    """ A message class used internally by the mailman to handle deferred
    delivery of messages. """
    def __init__(self, msg, intended_receiver):
        assert isinstance(msg, AgentMessage)
        super().__init__(sender=None, receiver=None, topic=self.__class__.__name__)
        self.deferred_message = msg
        self.intended_receiver = intended_receiver


class Agent(object):
    """ The default agent class. """
    def __init__(self, uuid=None):
        """
        :param uuid: None (default). Should only be set for inspection purposes. 
        """
        self.inbox = deque()      # when using self.receive() we get the messages from here
        self.outbox = deque()     # here we post messages when using self.send(msg)
        if uuid is None:
            self._uuid = uuid4().int   # this is our worldwide unique id.
        self.operations = dict()  # this is the link between msg.topic and agents response.
        self._is_setup = False    # this tells us that the agent is/ is not setup
        self._quit = False        # this tells the scheduler to kill the agent.
        self._time = 0            # the timestamp in the compute cycle.
        self.keep_awake = False   # this prevents the agent from entering sleep mode when there
                                  # are no new messages.

    @property
    def uuid(self):
        """
        :return: Returns the UUID of the agent. This is guaranteed to be volatile and unique.
        No two runs of the same simulation will have agents with the same UUID.
        """
        # if not hasattr(self, "uuid"):
        #     raise AttributeError("{} has no attribute self.uuid..! Have you remembered to run super().__init__() on the Agent class?".format(type(self)))
        return self._uuid

    @uuid.setter
    def uuid(self, value):
        raise ValueError("UUID cannot be set once the object has been instantiated")

    def __str__(self):
        return "<{}> UUID: {}".format(self.__class__.__name__, self._uuid)

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

        ! Runs automatically when the agent is added to the scheduler !

        A good approach is to use have functions for each message and register the
        functions in the Agent's class' operations at setup:

        def setup(self):
            self.subscribe(self.uuid)

            self.operations.update({"new request": self.new_request,
                                    "hello": self.receive_hello_msg})

            for topic in self.operations:
                self.subscribe(topic)

        Where appropriate, functions can to use numba's jit gcc compiler:

        @jit
        def new_request(self, msg):
            # do something.
            ...

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

        while self.messages():
            msg = self.receive()
            operation = self.operations.get(msg.get_topic())
            if operation is not None:
                operation(msg)
            else:
                self.logger("%s %s: don't know what to do with: %s" %
                            (self.__class__.__name__, str(self.get_uuid())[-6:], str(msg)),
                            log_level="DEBUG")

        if some messages take precedence over others (priority messages), the
        inbox should be emptied in the beginning of the update function for
        sorting. For example:

        priority_topics = [1,2,3]
        priority_messages = deque()  # from collections import deque
        normal_messages = deque()
        while self.messages():
            msg = self.receive()
            if msg.get_topic() in priority_topics:
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
        if not self._is_setup:
            self.setup()
            self._is_setup = True
        if not self._quit:
            self.update()
        if self._quit:
            self.teardown()

    def is_setup(self):
        """ A function used to check if the agent is setup."""
        return self._is_setup

    def logger(self, log_message, log_level='NOTSET'):
        """ A helper function so that people use message for logging and don't
        attempt to keep a file.io open as logging.getlogger normal does.
        :param message: Any message that is supposed to be logged.
        :param log_level: A valid log level. See LogMessage for details.
        :return: None
        """
        msg = LogMessage(sender=self, receiver=None, log_level=log_level, log_message=log_message)
        self.send(msg)

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

    def set_timed_alarm(self, alarm_time, alarm_message=None):
        """ A method to be used by the agent to set (and later receive) an alarm message.

        :param alarm_time: int, float: The time (from `self.now()` ) where the agent should
         receive the alarm message.
        :param alarm_message: AgentMessage that the agent should receive.
        """
        if alarm_message:
            assert isinstance(alarm_message, AgentMessage), "wake up message must be a subclass of agent message"
        assert isinstance(alarm_time, (int, float)), "wake up time must be int or float. Not {}".format(type(alarm_time))
        msg = AlarmMessage(sender=self, alarm_time=alarm_time, alarm_message=alarm_message)
        self.send(msg)

    def subscribe(self, topic):
        """
        A method to be used by the agent to set and subscribe to a particular topic
        :param topic: string
        
        Examples:
        
        To subscribe to messages for the agent itself, use [1]:
        topic=self.get_uuid())  
        
        To subscribe to messages for the agents own class (including class broadcasts), use [1]:
        topic=self.__class__.__name__ 
        
        To subscribe to messages of a particular subject, use:
        topic=AgentMessage.__class__.__name__
        
        [1] This option is loaded automatically at setup time. 
        
        """
        msg = SubscribeMessage(sender=self, subscription_topic=topic)
        self.send(msg=msg)

    def unsubscribe(self, topic):
        """ A method to be used by the agent to unset and unsubscribe to a particular topic
        :param topic: string 
        
        Note that all agents automatically unsubscribe at teardown.
        """
        msg = UnSubscribeMessage(sender=self, subscription_topic=topic)
        self.send(msg=msg)


class Sentinel(object):
    """
    A general sentinel object that can be used by Agents when iterating through
    deque's, queue's and lists.
    """
    def __init__(self):
        pass


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
        assert isinstance(clock_speed, (int, float, type(None))), "clock_speed must be int, float or None. Not: {}".format(type(clock_speed))
        super().__init__()
        self.keep_awake = True
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
        self.subscribe(SetTimeAndClockSpeedMessage.__name__)

    def teardown(self):
        pass

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
        self.time = msg.new_time
        self.clock_speed = msg.new_clock_speed

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
        if isinstance(new_clock_speed, (int,float)):
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
        assert isinstance(alarm_message, (type(None), AgentMessage)), "alarm_message must be None or instance of AgentMessage"
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
        if self.alarms:
            if self.clock_speed is None:
                right_now = self.time
            else:
                right_now = self.time + 1/self.clock_frequency

            while self.alarms:
                wake_up_time, uuid, msg = self.alarms[0]
                if wake_up_time <= right_now:
                    self.send(msg.wake_up_message)
                    self.alarms.pop(0)
                else: # wake_up_time > right now
                    break  # then the first alarm is in the future and there
                    # is no reason to look any further.
        else:
            pass  # there are no alarms.

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
            cfm = sum(self.clock_frequency_measurements)/len(self.clock_frequency_measurements)
        if cfm <= 0:
            cfm = 10**-9
        return 1/cfm

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
                self.logger("Scheduler requested clock to advance to next event,\nbut there are no more events.")
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
        else:
            alarm_message = AgentMessage(sender=sender, receiver=sender)
        self.wake_up_message = alarm_message


class MailMan(Agent):
    """
    The MailMan class receives mail from anyone controlled by the scheduler and
    relays it.
    """
    def __init__(self, message_monitor_horizon=10):
        super().__init__()
        self.keep_awake = True
        self.sentinel = Sentinel()
        self.agent_register = {}  # The agent register is a dict with
        # {agentuuid: agent instance} which is managed by the scheduler.
        # The mailman's methods self.add and self.remove are not execute
        # by the mailman itself.
        self.mailing_lists = {}
        self.operations.update({SubscribeMessage.__name__: self.process_subscribe_message,
                                UnSubscribeMessage.__name__: self.process_unsubscribe_message,
                                GetSubscriptionTopicsMessage.__name__: self.get_subscription_topics,
                                GetSubscribersMessage.__name__: self.get_subscriber_list,
                                DeferredDeliveryMessage.__name__: self.retry_deferred_delivery})
        # activity monitor
        self._message_monitor_horizon = message_monitor_horizon
        self._message_counter = deque(maxlen=message_monitor_horizon)
        self._message_counter_length = 0
        self._message_count_in_monitor_horizon = 0
        self._message_count = 0

    def setup(self):
        """ Sets up the mailman """
        self.add(self)  # registering one self so that mail can be handled.

    def teardown(self):
        """ Tears the mailman down."""
        message_dump = []
        while self.messages:
            message_dump.append(str(self.receive()))
        if message_dump:
            print("dumping MailMan's message queue as part of teardown:")
            print("\n".join(message_dump))

    def update(self):
        """ Updates the mailman (when the scheduler issue `agent.run()`
        :return: None
        """
        self.message_stats()
        self.inbox.append(self.sentinel)  # The best places to put a breakpoint...
        while self.messages:
            msg = self.receive()
            if msg is self.sentinel:
                break
            if not isinstance(msg, AgentMessage):
                self.logger(log_message="Discovered a faulty non-AgentMessage in the inbox. Message is dumped...",
                            log_level="WARN")
                continue  # this dumps the message as the mailman only handles AgentMessages.
            if isinstance(msg, AgentMessage):
                topic = msg.topic
                receiver = msg.receiver
                recipients = set()

                if receiver in self.mailing_lists:
                    recipients.update(self.mailing_lists[receiver])
                if topic in self.mailing_lists:  # then it's a tracked topic
                    recipients.update((self.mailing_lists[topic]))

                no_of_recipients = len(recipients)
                if no_of_recipients > 0:  # receiver is not in self.mailing_lists, so s/h/it might be moving.
                    self.send_to_recipients(msg=msg, recipients=recipients)
                elif topic in self.operations:  # broadcast receiver must be the mailman
                    self.to_mailman(msg)
                else:
                    self.logger(log_message="%s is not registered on a mailing list, so msg is saved the agent registers" % receiver, log_level="INFO")
                    self.defer_delivery(msg, receiver)

    def send_to_recipients(self, msg, recipients):
        """ Distributes AgentMessages to all registered recipients.
        :param msg: an instance of AgentMessage
        :param recipients: The registered recipients
        :return: Nont
        """
        if len(recipients) > 1:
            for recipient in recipients:  # this loop is necessary as a tracker may be on the reciever.
                msg_copy = deepcopy(msg)  # this is to prevent that anyone modifies a shared object...
                if recipient == self.uuid:  # the mailman might be on the subscriber list :-)
                    self.to_mailman(msg_copy)
                else:
                    self.send(msg_copy, receiver=recipient)
        else:
            recipient = list(recipients)[0]
            if recipient == self.uuid:  # the mailman might be on the subscriber list :-)
                self.to_mailman(msg)
            else:
                self.send(msg, receiver=recipient)

    def to_mailman(self, msg):
        """ A method used to send the message directly to the mailman.
        :param msg: AgentMessage
        :return: None
        """
        assert isinstance(msg, AgentMessage)
        topic = msg.topic
        if topic in self.operations:  # if the operation is known...
            operation = self.operations[topic]
            try:
                operation(msg)
            except Exception as e:
                self.logger(log_message="Mailman method '%s' broke with error %s" % (operation, e), log_level="WARNING")
        else:
            self.logger(log_message="Mailman does not have a method for %s" % str(msg), log_level="WARNING")

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
            self.logger(log_message="%s requesting topics added: %s" % (agent_uuid, subscription_topic), log_level="DEBUG")
        if agent_uuid not in self.mailing_lists[subscription_topic]:
            self.mailing_lists[subscription_topic].add(agent_uuid)
            if subscription_topic == agent_uuid:
                self.logger(log_message="%s subscribing to messages for itself." % (msg.sender), log_level="DEBUG")
            else:
                self.logger(log_message="%s subscribing to topic: %s" % (agent_uuid, subscription_topic), log_level="DEBUG")
        else:
            self.logger(log_message="%s already subscribing to topic: %s" % (agent_uuid, subscription_topic), log_level="DEBUG")

    def process_unsubscribe_message(self, msg):
        """ unsubscribes a subscriber from messages. Used by default during `_teardown` by all agents.
        :param msg: UnSubscribeMessage
        :return: None
        """
        assert isinstance(msg, UnSubscribeMessage)
        subscription_topic = msg.subscription_topic
        agent_uuid = msg.sender
        # remove subscriber from list
        if subscription_topic in self.mailing_lists:
            try:
                self.mailing_lists[subscription_topic].remove(agent_uuid)
            except IndexError:
                self.logger(log_message="%s never subscribed to topic: %s" % (agent_uuid, subscription_topic), log_level="DEBUG")
            except KeyError:
                self.logger(log_message="%s already removed from topic: %s" % (agent_uuid, subscription_topic), log_level="DEBUG")
            if len(self.mailing_lists[subscription_topic]) == 0:
                del self.mailing_lists[subscription_topic]
        else:
            self.logger(log_message="%s never subscribed to topic: %s" % (agent_uuid, subscription_topic), log_level="DEBUG")

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
        msg.subscription_topics = [t for t in self.mailing_lists.keys()]
        msg.receiver = msg.sender
        msg.sender = self
        self.send(msg)

    def send(self, msg, receiver=None):
        """ send overwrites the default Agent's send, as the mailman needs to handle
        a variety of situations."""
        assert isinstance(msg, AgentMessage)

        # 1. first we resolve who to send it to...
        if receiver is None:
            receiver = msg.receiver
            if receiver is None:  # receiver is None, so it's a broadcast.
                # If msg.get_receiver() also is None then something is wrong as
                # the mailman should have assigned a receiver before attempting
                # to send the message.
                return None  # dump the failed delivery.
        # 2. the we send it - if! - the receiver is reachable...
        if receiver in self.agent_register:
            try:
                agent = self.agent_register[receiver]
                agent.inbox.append(msg)
            except KeyError:
                self.logger(log_message="Delivery deferred. Mailman.agents has no registry of %s." % (receiver), log_level="DEBUG")
                # There are two cases where delivery is deferred:
                # a) Where the agent has not been added using Scheduler.add(agent). This is a usage error.
                # b) Where the agent is in another processor (multiprocess) and hence cannot be reached.
                self.defer_delivery(msg=msg, intended_receiver=receiver)
            except AttributeError:
                self.logger(log_message="%s doesn't have an inbox. Message dumped." % (receiver), log_level="ERROR")
        else:
            # 3. else we must defer delivery.
            self.logger(log_message="Receiver {} doesn't exist (yet). Message delivery is deferred.".format(receiver), log_level="DEBUG")
            self.defer_delivery(msg, receiver)

    def defer_delivery(self, msg, intended_receiver):
        """ Defer delivery handles attempts to put messages onto agents when they
        are not present, such as during multiprocessing, where agents are being
        updated on another compute core. See also `retry_deferred_delivery`"""
        assert isinstance(msg, AgentMessage), "Can't defer a non message..?!"
        self.logger(log_message="Delivery deferred until agent registers %s" % msg.receiver, log_level="DEBUG")
        msg.failed_delivery_attempt()
        if msg.delivery_attempts_left == 0:
            self.logger(log_message="Delivery has be re-attempted several times without success. Message is dumped", log_level="INFO")
        else:
            self.logger(log_message="Message {} has been deferred {} times".format(msg.uuid, msg.delivery_attempts_left), log_level="DEBUG")
            envelope = DeferredDeliveryMessage(msg, intended_receiver=intended_receiver)
            self.inbox.append(envelope)

    def retry_deferred_delivery(self, msg):
        """ The method defer_delivery produces a message which is added to the mailmans inbox.
        The DeferredDeliveryMessage is an envelope that is set for the intended receiver(!).
        Please note that the intended receiver, may not be the original receiver who could have been
        None or another uuid. For the broadcasting to work, the intended receiver is therefore
        recorded seperately in the envelope, whilst the original message remains unaltered.

        Should sending the original message fail after it has been unpacked from the envelope,
        then the parameter self.delivery_attempts will be incremented by the send method.

        This "closed loop" within the mailman assures that messages never are lost.

        For the case where the intended receiver is a mailinglist and no agent has yet subscribed
        to that mailinglist - for example during start up - the if-clauses below attempt
        to detect when the first subscriber to the mailinglist appears and then forward the
        messages

        :param msg: DeferredDeliveryMessage
        :return: None.
        """
        assert isinstance(msg, DeferredDeliveryMessage)
        original_message, intended_receiver = msg.deferred_message, msg.intended_receiver
        if intended_receiver not in self.agent_register.keys():  # this is commonly numeric.
            # then the intended receiver might be a mailinglist.
            if intended_receiver in self.mailing_lists.keys():  # this is commonly a string or numeric.
                self.inbox.append(original_message)
                return None
        self.send(original_message, intended_receiver)

    def add(self, agent):
        """ Adds an agent to the agent registry, so that messages can be received by
        the agent. The method is idempotent.
        :param agent: Agent
        :return: None
        """
        assert isinstance(agent, Agent)
        agent_uuid = agent.uuid
        self.agent_register[agent_uuid] = agent

        if agent_uuid not in self.mailing_lists:
            self.logger(log_message="%s (agent) registered to mailing list..." % agent_uuid, log_level="DEBUG")
        msg = SubscribeMessage(sender=agent, receiver=self, subscription_topic=agent_uuid)
        self.process_subscribe_message(msg)
        if agent.__class__.__name__ not in self.mailing_lists:
            self.logger(log_message="%s (class) registered to mailing list..." % agent.__class__, log_level="DEBUG")
        msg = SubscribeMessage(sender=agent, receiver=self, subscription_topic=agent.__class__.__name__)
        self.process_subscribe_message(msg)

    def remove(self, agent):
        """ Removes an agent from the agent registry, so that it no longer can receive
        messages. The method is idempotent.
        :param agent: Agent
        :return: None
        """
        assert isinstance(agent, Agent)
        uuid = agent.uuid
        for topic, mailinglist in self.mailing_lists.items():
            if uuid in mailinglist:
                msg = UnSubscribeMessage(sender=agent, receiver=None, subscription_topic=topic)
                self.inbox.append(msg)
        del self.agent_register[uuid]

    def message_stats(self):
        """ A counter that keeps track of messages. """
        new_message_count = len(self.inbox)
        if self._message_counter_length == self._message_monitor_horizon:
            removed_message_count = self._message_counter.popleft()
        else:
            removed_message_count = 0
            self._message_counter_length += 1
        self._message_count_in_monitor_horizon += (new_message_count - removed_message_count)
        self._message_counter.append(new_message_count)

    def is_idle(self):
        """ A method used to check if the mailman's job is done."""
        if self.messages:
            return False
        if self._message_counter_length < self._message_monitor_horizon:
            return False
        elif self._message_count_in_monitor_horizon > 0:
            return False
        return True


class Scheduler(Agent):
    """ The scheduler that handles updates of all agents."""
    def __init__(self, logfile=None, clock_speed=None, pause_if_idle=True,
                 number_of_multi_processors=multiprocessing.cpu_count(),
                 minimum_operating_frequency=1000):
        """

        :param logfile: A logfile (if available)
        :clock_speed: None, float or int: the simulation clock speed. 
        :param number_of_multi_processors: int: the number of processing cores.
        Default uses `multiprocessing.cpu_count()`. Any other string is interpreted
         as "False"
        :param pause_if_no_messages_for_n_iterations: int, Default setting for pausing the
         scheduler is 100 idle turns. Set to False if the scheduler should run as daemon.
        :param minimum_operating_frequency: Sets off an alarm if the ability to update all
        agents drops below the required operating frequency.
        """
        super().__init__()
        # init's self.inbox as a collections.deque() for various purposes
        assert isinstance(self.inbox, deque), "Scheduler can't work without a deque."
        assert isinstance(number_of_multi_processors, int)
        assert isinstance(pause_if_idle, bool)
        assert isinstance(minimum_operating_frequency, (float, int))
        self.shutdown_initiated = False

        # multiprocessing
        if number_of_multi_processors > 0:
            self.multiprocessing_tasks = multiprocessing.Queue()
            self.multiprocessing_results = multiprocessing.Queue()
            self.processor_pool = [Processor(name=str(p),
                                             task_queue=self.multiprocessing_tasks,
                                             result_queue=self.multiprocessing_results) for p in range(number_of_multi_processors)]
            for p in self.processor_pool:
                p.start()
            while not all([p.is_alive() for p in self.processor_pool]):
                time.sleep(0.01)
            for p in self.processor_pool:
                p.setup()
            self.multiprocessing = True
        else:
            self.multiprocessing = False

        # logging
        if logfile:
            if os.path.exists(logfile):
                print("writing logs to: {}".format(logfile))
                timestamp = time.asctime()
                timestamp = timestamp.replace(":", "-")
                timestamp = timestamp.replace(" ", "_")
                os.rename(logfile, logfile + timestamp)
        if logfile:
            logging.basicConfig(filename=logfile, filemode='w', level=logging.DEBUG)
        else:
            pass
        self.log = logging.getLogger(self.__class__.__name__)
        self.log.setLevel(LOG_LEVEL)
        if not self.log.handlers:
            ch = logging.StreamHandler(sys.stdout)
            ch.setLevel(LOG_LEVEL)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            ch.setFormatter(formatter)
            self.log.addHandler(ch)
        self.log.info("Scheduler is running with uuid: {}".format(self.uuid))

        self.pending_tasks = 0  # used to keep track of how many agents there are,
        # when agents are being updated in other processors during multiprocessing.
        self.iterations_to_halt = None
        self.message_count_in_cycle = 0  # used to count the number of agent
        # messages seen in an update cycle, so that the scheduler can sleep if
        # none of the agents are active.
        self.pause = False
        self.pause_if_idle = pause_if_idle

        self.operating_frequency = minimum_operating_frequency  # used to throttle
        # the sleep function if there is nothing to do.

        self.operations.update({PauseMessage.__name__: self.pause_msg,
                                StopMessage.__name__: self.initiate_shutdown,
                                StopConfirmationMessage.__name__: self.confirm_shutdown,
                                AddNewAgent.__name__: self.add_agent_from_message,
                                RemoveAgent.__name__: self.remove_agent_from_message,
                                LogMessage.__name__: self.write_log_msg_to_logger})

        # The processors are simple queues for tasks who receive an Agent, runs update
        # on it and returns it to the Scheduler.
        self.agents = deque()
        self.agents_to_be_deleted = set()

        # finalize the setup.
        self.sentinel = Sentinel()
        self.clock = Clock(clock_speed=clock_speed)
        self.mailman = MailMan()

        self.mailman.add(self)  # the scheduler must add itself to the mailmans
        # register, otherwise the mailman can't add messages to the scheduler's inbox.
        self.add(self.clock)  # launch in __init__
        self.add(self.mailman)
        for msgtype in self.operations.keys():
            self.subscribe(msgtype)

    def add(self, agent):
        """ Adds an agent to the scheduler
        :param agent: Agent
        """
        assert isinstance(agent, Agent)
        if self.multiprocessing:
            if agent not in (self.mailman, self.clock):
                try:
                    _ = pickle.dumps(agent)
                except Exception:
                    self.log.error("Agent could not be pickled: \n{}".format(str(agent)))
                    return
        self.log.debug("Registering agent {} {}".format(agent.__class__.__name__, agent.uuid))
        self.mailman.add(agent)  # self.agent_register[agent.uuid] = agent
        self.agents.append(agent)
        if not agent.is_setup():
            agent.subscribe(agent.uuid)
            agent.subscribe(agent.__class__.__name__)
            agent.setup()
            agent._is_setup = True
            self.send_and_receive(agent)

    def remove(self, agent):
        """ Removes an agent from the scheduler
        :param agent: Agent
        """
        if not isinstance(agent, Agent):  # if the provided information is the uuid, then
            # we must first identify the agent object.
            for _agent in self.agents:
                if _agent.uuid == agent:
                    agent = _agent
                    break
        if isinstance(agent, Agent):
            self.log.debug("DeRegistering agent {}".format(agent.uuid))
            if agent.is_setup():
                agent.unsubscribe(agent.uuid)
                agent.unsubscribe(agent.__class__.__name__)
                self._is_setup = False
                agent.teardown()
                self.send_and_receive(agent)
            self.mailman.remove(agent)  # del self.agent_register[agent.get_uuid()]
            self.agents_to_be_deleted.add(agent)  # When the scheduler updates itself, it
            # will look for agents that are to be deleted.
        else:
            self.log.error("Cannot remove unidentifiable agent: {}".format(agent))

    def setup(self):
        pass

    def teardown(self):
        """ Issues kill messages to the cpu workers and performs
        single threaded teardown."""
        for agent in self.agents:
            if agent is not self.sentinel:
                try:
                    assert isinstance(agent, Agent)
                    if agent.is_setup():
                        agent.teardown()
                        self.send_and_receive(agent)
                except NotImplementedError:
                    pass
        self.log.info("Teardown completed")

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
            if isinstance(seconds, (int,float)):
                right_now = self.clock.time
                pause_msg = PauseMessage(sender=self, receiver=self)
                to_msg = AlarmMessage(sender=self, alarm_time=seconds + right_now, alarm_message=pause_msg)
                self.send(to_msg)

        if iterations != '':
            assert isinstance(iterations, int), "iterations must an integer"
            self.iterations_to_halt = abs(iterations)
        else:
            self.iterations_to_halt = None

        if pause_if_idle in (False, True):
            self.pause_if_idle = pause_if_idle

        if self.pause:  # resetting self.pause if "run" is called.
            self.pause = False
        super().run()
        if self.pause:  # pause the clock.
            self.clock.pause()

    def stop(self):
        """
        Use this method to stop the simulation.
        """
        self.log.info("Scheduler shutdown initiated")
        msg = StopMessage(sender=self, receiver=self)
        self.initiate_shutdown(msg)

    def update(self):
        """ Once scheduler.run() is activated, the scheduler will remain in the
        main loop of update(). To stop the scheduler send a StopMessage.
        """
        if self.sentinel not in self.agents:
            self.agents.append(self.sentinel)  # we add the sentinel to make sure
            # that the scheduler checks its own messages from time to time.

        while not self._quit:
            agent = self.agents.popleft()  # the clock & sentinel will always be there...!
            if agent is self.sentinel:  # this makes the scheduler check it's own messages.
                self.agents.append(self.sentinel)
                self.time = self.clock.time
                self.scheduler_update()
                if self.pause:
                    self.log.debug("Pausing Scheduler, use 'run()' to continue. Use 'stop()' to shutdown remote processors.")
                    return None
                else:
                    continue
            assert isinstance(agent, Agent), "The scheduler can't run an update on a non-agent."
            if agent.keep_awake or agent.messages:
                if agent is not self.clock:
                    agent.time = self.clock.time
                if agent is self.clock or agent is self.mailman:
                    self.update_agent(agent)
                elif self.multiprocessing:
                    self.multiprocessing_tasks.put_nowait(agent)
                    self.pending_tasks += 1
                else:
                    self.update_agent(agent)
            else:
                self.agents.append(agent)

    def update_agent(self, agent):
        assert isinstance(agent, Agent)
        agent.run()
        self.send_and_receive(agent)
        self.agents.append(agent)

    def send_and_receive(self, agent):
        """ Transfers all outgoing messages from the agent to the mailman,
         so that subscriptions, monitoring & direct messages can be resolved.
        :param agent: type Agent
        """
        assert isinstance(agent, Agent)
        self.message_count_in_cycle += len(agent.outbox)
        while agent.outbox: # Send and receive the agents messages
            self.mailman.inbox.append(agent.outbox.popleft())

    def scheduler_update(self):
        """ Performs update on the scheduler itself."""
        if self.iterations_to_halt is not None:
            if self.iterations_to_halt > 0:
                self.iterations_to_halt -= 1
            elif self.iterations_to_halt == 0:
                self.pause = True

        # get agents in from the multiprocessing queue.
        if self.multiprocessing:
            agent = None
            while True:
                try:
                    agent = self.multiprocessing_results.get_nowait()
                except queue.Empty:
                    break

                if isinstance(agent, Agent):
                    self.agents.append(agent)  # Adds agents to main loop.
                    self.pending_tasks -= 1  # removes the agent from the pending tasks list.
                    self.send_and_receive(agent)  # this redirection of messages to the
                    # mailman also solves the issue of agents being unavailable for message
                    # reciept as the mailmans defer_delivery method handles this gracefully.
                    # as the mailman NEVER leaves the schedulers main loop.
                elif isinstance(agent, AgentMessage):
                    self.inbox.append(agent)

        # get agents in own inbox:
        while self.messages:
            msg = self.receive()
            if isinstance(msg, AgentMessage):
                operation = self.operations.get(msg.topic)
                if operation is not None:
                    operation(msg)
                else:
                    self.mailman.inbox.append(msg)  # if the scheduler doesn't know what to
                    # with the message, then it is up to the mailman to resolve the problem.
                    # the scheduler merely "dumps" the message to the mailman.
            else:
                pass # dumps the package quietly.

        # send own messages:
        self.send_and_receive(self)

        # maintain agent pool.
        for agent in self.agents_to_be_deleted:
            if agent in self.agents:
                self.agents.remove(agent)

        # if the clockspeed is None, but alarms are pending and the mailman is idle,
        # then a jump in time is appropriate:
        if all([self.mailman.is_idle(),
                self.clock.is_waiting_for_the_alarm_clock(),
                self.clock.clock_speed is None,
                self.pending_tasks == 0]):
            self.clock.advance_time_to_next_timed_event(issue_stop_message_if_no_more_events=self.pause_if_idle)

        # if the mailman and clock are idle, then the scheduler should pause.
        if all([self.mailman.is_idle(),
                self.clock.is_idle(),
                self.pause_if_idle]):
            self.pause = True

        # if no new messages have been seen, then sleep for a moment as the
        # scheduler either:
        # a) Is running in real-time and is waiting for some external event.
        # b) Is waiting for a coprocessor to finish work.
        if self.clock.clock_speed and self.message_count_in_cycle == 0:
            time.sleep(1/self.operating_frequency)
        self.message_count_in_cycle = 0

    def initiate_shutdown(self, msg):
        """
        Sends out shutdown messages to all agents and assures that
        all agents have completed teardown before killing own process.
        :param: StopMessage
        :return: None
        """

        # These checks assures that the stop is intended for the scheduler and not some accidental broadcast.
        assert isinstance(msg, StopMessage)
        assert msg.receiver == self.uuid, "The Scheduler received a StopMessage, but wasn't the intended receiver..!"

        if self.multiprocessing:
            for p in self.processor_pool:
                stop_msg = StopMessage(sender=self, receiver=p.name)
                self.multiprocessing_tasks.put_nowait(stop_msg)
            self.shutdown_initiated = True
            while self.processor_pool:
                self.scheduler_update()
        else:  # single processor
            self._quit = True
            self.shutdown_initiated = True
        self.log.debug("Scheduler shutdown complete.")

    def confirm_shutdown(self, msg):
        """
        Receives message from the coprocessors.
        :param msg: StopConfirmationMessage
        :return: None
        """
        assert isinstance(msg, StopConfirmationMessage)
        to_be_removed = []
        for p in self.processor_pool:
            if p.name == msg.sender:
                to_be_removed.append(p)
        for p in to_be_removed:
            self.processor_pool.remove(p)
            p.join()
            self.log.info("Scheduler received shutdown confirmation from {}".format(p.name))
        if not self.processor_pool:
            self._quit = True

    def pause_msg(self, msg):
        """
        Pauses update of agents until "start" is received.
        msg: PauseMessage
        """
        assert isinstance(msg, PauseMessage)
        if msg.receiver == self.uuid:
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
        assert isinstance(agent, (int, Agent))
        self.remove(agent)

    def write_log_msg_to_logger(self, msg):
        """ Writes a log message out to logfile (stdout)
        :param msg: LogMessage
        :return: None
        """
        assert isinstance(msg, LogMessage)
        level = logging._nameToLevel[msg.log_level]
        assert isinstance(level, int)
        self.log.log(level=level, msg=msg.log_message)


class AddNewAgent(AgentMessage):
    def __init__(self, sender, agent, receiver=Scheduler.__name__):
        super().__init__(sender=sender, receiver=receiver)
        assert isinstance(agent, Agent)
        self.agent = agent


class RemoveAgent(AgentMessage):
    def __init__(self, sender, agent_or_agent_uuid, receiver=Scheduler.__name__):
        super().__init__(sender=sender, receiver=receiver)
        self.agent_to_be_removed = agent_or_agent_uuid


class StopConfirmationMessage(AgentMessage):
    def __init__(self, sender, receiver):
        super().__init__(sender=sender, receiver=receiver)


class Processor(multiprocessing.Process):  # class Processor(multiprocessing.Process):
    def __init__(self, name, task_queue, result_queue):
        # multiprocessing setup.
        multiprocessing.Process.__init__(self, name=name)  # multiprocessing.Process.__init__(self)
        self.exit = multiprocessing.Event()  # self.exit = multiprocessing.Event()
        self.inbox = deque()  # the process' private inbox.
        self.task_queue = task_queue  # a multiprocessing.Queue  - a public FIFO inbox.
        self.result_queue = result_queue  # the schedulers inbox
        self.daemon = False

        # agent setup.
        self.operations = {StopMessage.__name__: self.stop}
        self.is_setup = False
        self._quit = False

    def logger(self, message, log_level='NOTSET'):
        msg = LogMessage(sender=self.name, receiver=None, log_message=message, log_level=log_level)
        self.result_queue.put(msg)

    def stop(self, msg):
        assert isinstance(msg, StopMessage)
        if msg.receiver == self.name:
            # print("Process {} got the stop signal..".format(self.name), end='', flush=True)
            self._quit = True
            stop_response_msg = StopConfirmationMessage(sender=self.name, receiver=msg.sender)
            self.result_queue.put_nowait(stop_response_msg)
            self.exit.set()
        else:  # if the message is not for me, then I merely put it back.
            self.task_queue.put_nowait(msg)

    def setup(self):
        self.is_setup = True
        # more setup functions can be patched in here if necessary.

    def teardown(self):
        pass

    def messages(self):
        if len(self.inbox) > 0:
            return True
        else:
            return False

    def receive(self):
        try:
            return self.inbox.popleft()
        except IndexError:
            pass

    def run(self):
        if not self.is_setup:
            self.setup()  # the processor doesn't have the private self._setup() method that agents have.
        if not self._quit:
            try:
                self.update()
            except Exception as e:
                self.logger(log_level="WARN", message=str(e))
                self._quit = True
        if self._quit:
            self.teardown()
        else:
            pass

    def update(self):
        found_work = False
        while not self._quit:
            # 1) Check the inqueue and do 1 unit of work.
            task = None
            try:
                task = self.task_queue.get_nowait()
                found_work = True
            except queue.Empty:
                found_work = False

            if isinstance(task, AgentMessage):
                self.inbox.append(task)
            elif isinstance(task, Agent):
                task.run()  # this runs the Agent's update method.
                self.result_queue.put_nowait(task)  # this returns the Agent to the scheduler, with messages in the Agents outbox.
            else:
                pass  # there is nothing to do.

            # 2) Check own messages
            while self.messages():
                msg = self.receive()
                self.logger(message="Got: {}".format(str(msg)), log_level="INFO")
                assert isinstance(msg, AgentMessage)
                operation = self.operations.get(msg.topic)
                if operation is not None:
                    operation(msg)
                else:
                    pass
                if not found_work:
                    found_work = True
            else:
                found_work = False

            # 3) If there was no work, then sleep to save power.
            if not found_work:
                time.sleep(randint(1,10)/100.0)


