import time
import logging
from collections import deque, defaultdict
from itertools import count
from bisect import insort

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
        raise NotImplementedError("subclasses must implement a suitable copy method.")

    @property
    def topic(self):
        """
        :return: The topic of the message. Typically the saame as Message.__class__.__name__
        """
        return self._topic

    @topic.setter
    def topic(self, topic):
        self._topic = topic


class Agent(object):
    """ The default agent class. """
    uuid_counter = count(1)

    def __init__(self, uuid=None):
        """
        :param uuid: None (default). Should only be set for inspection purposes.
        """
        self.inbox = deque()  # when using self.receive() we get the messages from here
        if uuid is None:
            self._uuid = next(Agent.uuid_counter)  # this is our worldwide unique id.
        else:
            try:
                _ = hash(uuid)
            except TypeError:
                raise TypeError("uuid must be hashable.")
            self._uuid = uuid
        self._scheduler_api = None
        self.operations = dict()  # this is the link between msg.topic and agents response.
        self.keep_awake = False  # this prevents the agent from entering sleep mode when there
        # are no new messages.

    @property
    def uuid(self):
        """
        :return: Returns the UUID of the agent.

        beginner errors:
        Q: Agent does not have attribute "uuid".
        A: You forgot to run super().__init__() on the Agent class.
        """
        return self._uuid

    @uuid.setter
    def uuid(self, value):
        raise ValueError("UUID cannot be set once the object has been instantiated")

    def __str__(self):
        return f"{self.__class__.__name__}({self.uuid})"

    def __repr__(self):
        return f"{self.__class__.__name__}({self.uuid})"

    def send(self, msg):
        """ The only method for sending messages in the system.
        Message are deliberately NOT asserted for, as it should be possible
        to dispatch all kinds of objects.
        :param msg: any pickleable object.
        :return: None
        """
        assert isinstance(msg, AgentMessage), "sending messages that aren't based on AgentMessage's wont work"
        assert isinstance(self._scheduler_api, Scheduler), "agent must be added to scheduler using scheduler.add(agent)"
        self._scheduler_api.mail_queue.append(msg)

    @property
    def messages(self):
        """
        :return: Boolean: True if there are messages.
        """
        if self.inbox:
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
        pass

    def teardown(self):
        """Users can implement this teardown method for shutting down the kernel agent.

        ! Runs automatically when the agent is removed from the scheduler !

        """
        pass

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
                text = "{} {}: don't know what to do with: {}".format(
                    self.__class__.__name__, str(uuid), str(msg)
                )
                self.logger(text, log_level="DEBUG")

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

    def log(self, msg, level=NOTSET):
        """
        :param msg: str or AgentMessage
        :param level: int
        :return:
        """
        assert isinstance(self._scheduler_api, Scheduler)
        self._scheduler_api.log(level, msg)

    def set_alarm(self, alarm_time, alarm_message, relative=True, ignore_alarm_if_idle=True):
        """ delivers alarm_message to alarm_message.receiver at alarm_time (relative or absolute)

        NB: alarm_message.receiver does not have to be self. An agent can create a message and
        set_alarm(..., msg, ...) with a message where the receiver is another agent.

        :param alarm_time: float: time as timestamp()
        :param alarm_message: AgentMessage, if None the scheduler will run "update" on the agent once.

        :param relative: boolean (1 second later is relative)
            True: alarm goes off at time.time() + alarm_time
            False: alarm goes off at alarm_time (must be greater than time.time() )
        :param ignore_alarm_if_idle: boolean, if True, the scheduler will ignore that an alarm was set,
        if there are no more messages being exchanged.
        """
        if not isinstance(alarm_time, (float, int)):
            raise TypeError("expected float or int time. Use time.time() or datetime.datetime.now().timestamp()")
        if not isinstance(alarm_message, AgentMessage):
            raise TypeError("expected AgentMessage")

        assert isinstance(self._scheduler_api, Scheduler), "agent must be added to scheduler using scheduler.add(agent)"
        self._scheduler_api.set_alarm(alarm_time=alarm_time,
                                      alarm_message=alarm_message,
                                      relative=relative,
                                      ignore_alarm_if_idle=ignore_alarm_if_idle)

    def remove_alarm(self, alarm_message=None):
        """
        :param alarm_message: optional, if provided, the alarm associated with the given message is removed.
            if not provided, all previously set alarms are removed.
        :param if specified only alarms with set topic are removed.
            otherwise all alarms for this agent are removed.
        """
        self._scheduler_api.clear_alarms(uuid=self.uuid, alarm_message=alarm_message)

    def subscribe(self, uuid=None, topic=None):
        """
        :param uuid: optional, the uuid of the agent that self wants to subscribe to.
        :param topic: optional, the topic of the message that self want to subscribe to.

        A method to be used by the agent to set and subscribe to a particular topic

        Examples:
        To subscribe to messages for the agent itself, use: topic=self.uuid

        To subscribe to messages for the agents own class (including class broadcasts),
        use: topic=self.__class__.__name__

        To subscribe to messages of a particular subject, use:
        topic=AgentMessage.__class__.__name__

        """
        assert isinstance(self._scheduler_api, Scheduler), "agent must be added to scheduler using scheduler.add(agent)"
        self._scheduler_api.subscribe(subscriber=self.uuid, target=uuid, topic=topic)

    def unsubscribe(self, target=None, topic=None):
        """ A method to be used by the agent to unset and unsubscribe to a particular topic
        :param target: string or None. If None, the agent unsubscribes to topic.
        :param topic: string or None. If None, the agent unsubscribes from everything.

        Note that all agents automatically unsubscribe at teardown.
        """
        assert isinstance(self._scheduler_api, Scheduler), "agent must be added to scheduler using scheduler.add(agent)"
        self._scheduler_api.unsubscribe(subscriber=self.uuid, target=target, topic=topic)

    def get_subscriber_list(self, target=None, topic=None):
        assert isinstance(self._scheduler_api, Scheduler), "agent must be added to scheduler using scheduler.add(agent)"
        return self._scheduler_api.get_subscriber_list(target=target, topic=topic)

    def get_subscription_topics(self):
        assert isinstance(self._scheduler_api, Scheduler), "agent must be added to scheduler using scheduler.add(agent)"
        return self._scheduler_api.get_subscription_topics()

    def pause(self):
        """ Tells the scheduler to stop at the end of the update cycle. """
        assert isinstance(self._scheduler_api, Scheduler), "agent must be added to scheduler using scheduler.add(agent)"
        self._scheduler_api.pause()

    def add(self, agent):
        """ Adds the agent to the scheduler. """
        assert isinstance(agent, Agent)
        assert isinstance(self._scheduler_api, Scheduler), "agent must be added to scheduler using scheduler.add(agent)"
        self._scheduler_api.add(agent)

    def remove(self, uuid):
        """ Removes the agent from the scheduler. """
        assert isinstance(self._scheduler_api, Scheduler), "agent must be added to scheduler using scheduler.add(agent)"
        self._scheduler_api.remove(uuid)


class SchedulerException(MasLiteException):
    pass


class Clock(object):
    def __init__(self, scheduler_api):
        if not isinstance(scheduler_api, Scheduler):
            raise TypeError
        self.scheduler_api = scheduler_api
        self._time = None
        self.alarms = []
        self.alarm_messages = defaultdict(list)
        self.last_required_alarm = -1

    @property
    def time(self):
        return self._time

    def __str__(self):
        return f"{self.__class__.__name__}: {self.time} {len(self.alarms)} alarms pending"

    def tick(self):
        """ progresses time by one tick."""
        raise NotImplementedError("sub classes implement this so that _time is updated.")

    def release_alarm_messages(self):
        for timestamp in self.alarms:  # alarms are already sorted.
            if timestamp > self._time:
                return
            self.scheduler_api.mail_queue.extend(self.alarm_messages[timestamp][:])
            del self.alarm_messages[timestamp]
            self.alarms.remove(timestamp)

    def set_alarm(self, delay, signal, ignore_alarm_if_idle):
        assert isinstance(delay, (int, float))
        assert isinstance(signal, AgentMessage)
        assert isinstance(ignore_alarm_if_idle, bool)
        wakeup_time = self.time + delay
        if ignore_alarm_if_idle is False:
            self.last_required_alarm = max(self.last_required_alarm, wakeup_time)
        insort(self.alarms, wakeup_time)  # smallest first!
        self.alarm_messages[wakeup_time].append(signal)

    def clear_alarms(self, uuid=None, message=None):
        """
        :param uuid: setter of the alarm.
        :param message: alarm message to be removed.
        """
        if message is not None:  # the long way.
            for timestamp in self.alarm_messages.copy():
                self.alarm_messages[timestamp] = [s for s in self.alarm_messages[timestamp] if s != message]
        elif uuid is not None:
            for timestamp in self.alarm_messages.copy():
                self.alarm_messages[timestamp] = [s for s in self.alarm_messages[timestamp] if s.receiver != uuid]
        else:
            self.alarms.clear()
            self.alarm_messages.clear()


class RealTimeClock(Clock):
    def __init__(self, scheduler_api):
        super().__init__(scheduler_api)
        self._time = time.time()

    def tick(self):
        self._time = time.time()


class SimulationClock(Clock):
    def __init__(self, scheduler_api):
        super().__init__(scheduler_api)
        self._time = 0

    def tick(self):
        if self.scheduler_api.needs_update:
            pass  # don't progress time, agents are updating.
        elif self.alarms:  # jump in time to the next alarm.
            self._time = min(self.alarms)
        else:
            pass


class Scheduler(object):
    """ The scheduler that handles updates of all agents."""

    def __init__(self, logger=None, real_time=True):
        """
        :param logger: optional: logging.logger
        """
        if real_time:
            self.clock = RealTimeClock(scheduler_api=self)
        else:
            self.clock = SimulationClock(scheduler_api=self)
        self.mail_queue = deque()
        self.mailing_lists = defaultdict(set)
        self.agents = dict()
        self.needs_update = set()
        self.has_keep_awake = set()
        self._must_run_until_alarm_expires = False

        self._quit = False
        self._operating_frequency = 1000

        if logger is None:
            self._logger = logging.getLogger(self.__class__.__name__)
            self._logger.setLevel(LOG_LEVEL)
            self._logger.propagate = False
            if not any(isinstance(h, logging.StreamHandler) for h in self._logger.handlers):
                handler = logging.StreamHandler()
                handler.setLevel(LOG_LEVEL)
                self._logger.addHandler(handler)
        else:
            self._logger = logger

    def __str__(self):
        return f"{self.__class__.__name__} ({len(self.needs_update)}/{len(self.agents)} agents active)"

    def log(self, level, msg):
        self._logger.log(level, msg)

    def add(self, agent):
        """ Adds an agent to the scheduler
        :param agent: Agent
        """
        assert isinstance(agent, Agent)
        self.log(level=DEBUG, msg="Registering agent {} {}".format(agent.__class__.__name__, agent.uuid))
        if agent.uuid in self.agents:
            raise SchedulerException("Agent uuid already in usage.")
        self.agents[agent.uuid] = agent
        agent._scheduler_api = self
        self.subscribe(subscriber=agent.uuid, target=agent.uuid)
        self.subscribe(subscriber=agent.uuid, topic=agent.__class__.__name__)
        agent.setup()

        if agent.keep_awake:
            self.has_keep_awake.add(agent.uuid)
        self.needs_update.add(agent.uuid)

    def remove(self, agent_or_uuid):
        """ Removes an agent from the scheduler
        :param agent_or_uuid: Agent or uuid of the agent.
        """
        if not isinstance(agent_or_uuid, Agent):
            agent = self.agents.get(agent_or_uuid, None)
            if agent is None:
                raise ValueError("Agent not found: {}".format(agent_or_uuid))
        else:
            agent = agent_or_uuid
        assert isinstance(agent, Agent)

        if agent.uuid not in self.agents:
            self.log(level=DEBUG, msg="Agent exists but hasn't been added: {}".format(agent_or_uuid))
            return

        self.log(level=DEBUG, msg="DeRegistering agent {}".format(agent.uuid))
        agent.teardown()
        self.unsubscribe(subscriber=agent.uuid, target=None, topic=None)
        if agent.uuid in self.needs_update:
            self.needs_update.remove(agent.uuid)
        if agent.uuid in self.has_keep_awake:
            self.has_keep_awake.remove(agent.uuid)
        del self.agents[agent.uuid]

    def run(self, seconds=None, iterations=None, pause_if_idle=True, clear_alarms_at_end=True):
        """ The main 'run' operation of the Scheduler.

        :param seconds: float, int, None: optional number of real-time seconds to run.
        :param iterations: float, int, None: feature to let the scheduler run for
        N (`iterations`) updates before pausing.
        :param pause_if_idle: boolean: default=False: If no new messages are exchanged
        the scheduler's clock will tick along as any other real-time system.
        If pause_if_idle is set to True, the scheduler will pause once the message queue
        is idle.
        :param clear_alarms_at_end: boolean: deletes any alarms if paused.

        Depending on which of 'seconds' or 'iterations' occurs first, the simulation
        will be paused.
        """
        start_time = None
        if isinstance(seconds, (int, float)) and seconds > 0:
            start_time = time.time()

        iterations_to_halt = None
        if isinstance(iterations, int) and iterations > 0:
            iterations_to_halt = abs(iterations)

        assert isinstance(pause_if_idle, bool)
        assert isinstance(clear_alarms_at_end, bool)

        # check all agents for messages (in case that someone on the outside has added messages).
        updated_agents = {agent.uuid for agent in self.agents.values() if agent.inbox or agent.keep_awake}
        self.needs_update.update(updated_agents)
        self.process_mail_queue()

        # The main loop of the scheduler:
        self._quit = False
        while not self._quit:  # _quit is set by method self.pause() and can be called by any agent.

            # update the agents. process.
            self.needs_update.update(self.has_keep_awake)
            for uuid in self.needs_update:
                agent = self.agents[uuid]
                agent.update()
                if agent.keep_awake:
                    self.has_keep_awake.add(agent.uuid)
                else:
                    self.has_keep_awake.discard(agent.uuid)
            self.needs_update.clear()

            # check any timed alarms.
            self.clock.tick()
            self.clock.release_alarm_messages()

            # distribute messages or sleep.
            no_messages = len(self.mail_queue) == 0
            if self.mail_queue:
                self.process_mail_queue()

            # determine whether to stop:
            if start_time is not None:
                if time.time() >= (start_time + seconds):
                    self._quit = True

            if iterations_to_halt is not None:
                iterations_to_halt -= 1
                if iterations_to_halt <= 0:
                    self._quit = True

            if no_messages:
                if self.clock.time < self.clock.last_required_alarm:
                    time.sleep(1 / self._operating_frequency)
                elif pause_if_idle:
                    self._quit = True
                else:
                    pass  # nothing to do.

        if clear_alarms_at_end:
            self.clock.clear_alarms()

    def process_mail_queue(self):
        """
        distributes the mail, so that when the scheduler pauses, new users
        can debug the agents starting with their fresh state with new messages.
        """
        for msg in self.mail_queue:
            assert isinstance(msg, AgentMessage)
            topic = msg.topic
            receiver = msg.receiver
            recipients = set()
            # 1. collect the list of recipients

            if (None, receiver) in self.mailing_lists:  # then it's a tracked receiver.
                recipients.update(self.mailing_lists[(None, receiver)])

            if (topic, None) in self.mailing_lists:  # then it's a tracked topic
                recipients.update(self.mailing_lists[(topic, None)])

            if (topic, receiver) in self.mailing_lists:  # then it's tracked topic and receiver.
                recipients.update(self.mailing_lists[(topic, receiver)])

            # 2. distribute the mail.
            if recipients:  # receiver is not in self.mailing_lists, so s/h/it might be moving.
                self.send_to_recipients(msg=msg, recipients=recipients)
            else:
                self.log(level=DEBUG, msg="{} is not registered on a mailing list.".format(receiver))
        self.mail_queue.clear()

    def send_to_recipients(self, msg, recipients):
        """ Distributes AgentMessages to all registered recipients.
        :param msg: an instance of AgentMessage
        :param recipients: The registered recipients
        """
        for uuid in recipients:  # this loop is necessary as a tracker may be on the receiver.
            agent = self.agents.get(uuid, None)
            if agent is None:
                continue
            self.needs_update.add(uuid)
            if msg.receiver == uuid:
                agent.inbox.append(msg)  # original message
            else:
                msg_copy = msg.copy()
                agent.inbox.append(msg_copy)

    def pause(self):
        self._quit = True

    def set_alarm(self, alarm_time, alarm_message, relative, ignore_alarm_if_idle):
        """
        :param alarm_time: time for the alarm (relative or absolute)
        :param alarm_message: AgentMessage.
        :param relative: bool: if true, alarm_time = clock.time + alarm_time
                                else, alarm_time is taken as an absolute value
        :param ignore_alarm_if_idle: Allows the scheduler to stop if no other messages are exchanged.
        """
        if relative:
            delay = alarm_time
        else:
            delay = alarm_time - self.clock.time

        if delay < 0:
            raise ValueError("Alarm time is in the past")

        self.clock.set_alarm(delay=delay, signal=alarm_message, ignore_alarm_if_idle=ignore_alarm_if_idle)

    def subscribe(self, subscriber, target=None, topic=None):
        """ subscribe lets the Agent react to SubscribeMessage and adds the subscriber.
        to registered subscribers. Used by default during `_setup` by all agents.
        :param subscriber: the agent uuid listening to messages
        :param target: the agent receiving messages
        :param topic: the topic received by the target

        Notes: The method adds agent to subscriber list.
        Any agent may subscribe for the same topic many times (this is managed)
        """
        if subscriber not in self.agents:
            raise ValueError(f"subscriber {subscriber} unknown")

        key = (topic, target)
        if key not in self.mailing_lists:
            self.log(level=DEBUG, msg=f"topic added: {topic}")

        if subscriber not in self.mailing_lists[key]:
            self.mailing_lists[key].add(subscriber)
            self.log(level=DEBUG, msg=f"{subscriber} subscribing to topic: {key}")
        else:
            self.log(level=DEBUG, msg=f"{subscriber} already subscribing to topic: {key}")

    def unsubscribe(self, subscriber, target=None, topic=None):
        """ unsubscribes a subscriber from messages.
        :param subscriber: the agent uuid listening to messages
        :param target: the agent receiving messages
        :param topic: the topic received by the target
        """
        if any((topic, target)):
            key = (topic, target)
            self.mailing_lists[key].discard(subscriber)
            if len(self.mailing_lists[key]) == 0:
                del self.mailing_lists[key]
        else:  # the long way
            keys = [key for key, subscribers in self.mailing_lists.items() if subscriber in subscribers]
            for key in keys:
                self.mailing_lists[key].discard(subscriber)
                if not self.mailing_lists[key]:
                    del self.mailing_lists[key]

    def get_subscriber_list(self, target=None, topic=None):
        """ Returns the list of subscribers of a particular topic for particular topics.
        :param target: the agent receiving messages
        :param topic: the topic received by the target
        :return list of subscribers
        """
        key = (topic, target)
        return [i for i in self.mailing_lists.get(key)]

    def get_subscription_topics(self):
        """ Returns the list of subscription topics"""
        return [t for t in self.mailing_lists.keys()]


