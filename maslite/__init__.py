import time, datetime
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
        assert isinstance(self._scheduler_api, Scheduler), "agent must be added to scheduler using scheduler.add(agent)"
        self._scheduler_api.mail_queue.append(msg)

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

    def log(self, msg, level=NOTSET):
        """
        :param msg: str or AgentMessage
        :param level: int
        :return:
        """
        assert isinstance(self._scheduler_api, Scheduler)
        self._scheduler_api.log(level, msg)

    def set_alarm(self, alarm_time, alarm_message=None, relative=False, ignore_alarm_if_idle=True):
        """ to set alarms

        :param alarm_time: time as timestamp() (float)
        :param alarm_message: AgentMessage, if None the scheduler will run "update" on the agent once.
        :param relative: boolean (1 second later is relative)
            True: alarm goes off at time.time() + alarm_time
            False: alarm goes off at alarm_time (must be greater than time.time() )
        :param ignore_alarm_if_idle: boolean, if True, the scheduler will ignore that an alarm was set,
        if there are no more messages being exchanged.
        """
        assert isinstance(alarm_time, (float, int)), "expected float or int time. Use time.time() or datetime.datetime.now().timestamp()"
        now = time.time()
        if relative:
            alarm_time = now + alarm_time

        if alarm_time < now:
            raise ValueError("Alarm time is in the past")
        assert isinstance(self._scheduler_api, Scheduler), "agent must be added to scheduler using scheduler.add(agent)"
        self._scheduler_api.set_alarm(uuid=self.uuid, alarm_time=alarm_time,
                                      alarm_message=alarm_message,
                                      ignore_alarm_if_idle=ignore_alarm_if_idle)

    def subscribe(self, topic):
        """
        A method to be used by the agent to set and subscribe to a particular topic
        :param topic: string

        Examples:
        To subscribe to messages for the agent itself, use: topic=self.uuid

        To subscribe to messages for the agents own class (including class broadcasts),
        use: topic=self.__class__.__name__

        To subscribe to messages of a particular subject, use:
        topic=AgentMessage.__class__.__name__

        """
        assert isinstance(self._scheduler_api, Scheduler), "agent must be added to scheduler using scheduler.add(agent)"
        self._scheduler_api.subscribe(uuid=self.uuid, topic=topic)

    def unsubscribe(self, topic=None):
        """ A method to be used by the agent to unset and unsubscribe to a particular topic
        :param topic: string or None. If None, the agent unsubscribes from everything.

        Note that all agents automatically unsubscribe at teardown.
        """
        assert isinstance(self._scheduler_api, Scheduler), "agent must be added to scheduler using scheduler.add(agent)"
        self._scheduler_api.unsubscribe(uuid=self.uuid, topic=topic)

    def get_subscriber_list(self, topic):
        assert isinstance(self._scheduler_api, Scheduler), "agent must be added to scheduler using scheduler.add(agent)"
        return self._scheduler_api.get_subscriber_list(topic)

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


class Alarm(object):
    """ Data structure for the Schedulers alarm"""
    __slots__ = ['uuid', 'alarm_time', 'alarm_message', 'ignore_alarm_if_idle']

    def __init__(self, uuid, alarm_time, alarm_message, ignore_alarm_if_idle):
        self.uuid = uuid
        self.alarm_time = alarm_time
        self.alarm_message = alarm_message
        self.ignore_alarm_if_idle = ignore_alarm_if_idle


class Scheduler(object):
    """ The scheduler that handles updates of all agents."""

    def __init__(self, logger=None):
        """
        :param logger: optional: logging.logger
        """
        self.mail_queue = deque()
        self.mailing_lists = {}
        self.agents = dict()
        self.needs_update = set()
        self.has_keep_awake = set()
        self.alarms = []
        self._must_run_until_alarm_expires = False

        self._quit = False
        self._operating_frequency = 1_000

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
        # give agent a child logger with name structure "Scheduler.AgentClass"
        agent._scheduler_api = self
        self.subscribe(agent.uuid, topic=agent.uuid)
        self.subscribe(agent.uuid, topic=agent.__class__.__name__)
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
        self.unsubscribe(agent.uuid)
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
            self.check_alarms()

            # distribute messages or sleep.
            no_messages = len(self.mail_queue) == 0
            if self.mail_queue:
                self.process_mail_queue()

            # determine whether to stop:
            if start_time is not None:
                now = time.time()
                if now >= (start_time + seconds):
                    self._quit = True

            if iterations_to_halt is not None:
                if iterations_to_halt > 0:
                    iterations_to_halt -= 1
                if iterations_to_halt == 0:
                    self._quit = True

            if no_messages:
                if self._must_run_until_alarm_expires is True:
                    time.sleep(1 / self._operating_frequency)
                elif pause_if_idle:
                    self._quit = True

        if clear_alarms_at_end:
            self.alarms.clear()

    def process_mail_queue(self):
        """
        distributes the mail, so that when the scheduler pauses, new users
        can debug the agents starting with their fresh state with new messages.
        """
        while self.mail_queue:
            msg = self.mail_queue.popleft()
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

    def send_to_recipients(self, msg, recipients):
        """ Distributes AgentMessages to all registered recipients.
        :param msg: an instance of AgentMessage
        :param recipients: The registered recipients
        """
        for uuid in recipients:  # this loop is necessary as a tracker may be on the reciever.
            agent = self.agents.get(uuid, None)
            if agent is None:
                continue
            self.needs_update.add(uuid)
            if len(recipients) == 1:
                agent.inbox.append(msg)
            else:
                agent.inbox.append(msg.copy())  # deepcopy is used to prevent that anyone modifies a shared object...

    def pause(self):
        self._quit = True

    def set_alarm(self, uuid, alarm_time, alarm_message, ignore_alarm_if_idle):
        now = time.time()
        assert alarm_time > now, "Alarm time is in the past"
        self.alarms.append(Alarm(uuid, alarm_time, alarm_message, ignore_alarm_if_idle))
        self.alarms.sort(key=lambda x: x.alarm_time)
        if ignore_alarm_if_idle is False:
            self._must_run_until_alarm_expires = True

    def check_alarms(self):
        now = time.time()
        expired_alarms = [a for a in self.alarms if now >= a.alarm_time]
        if not expired_alarms:
            return
        self.alarms = [a for a in self.alarms if now < a.alarm_time]
        self._must_run_until_alarm_expires = any((a for a in self.alarms if a.ignore_alarm_if_idle is False))
        for alarm in expired_alarms:
            assert isinstance(alarm, Alarm)
            agent = self.agents.get(alarm.uuid, None)
            if agent is None:  # agent could have been removed.
                continue
            self.needs_update.add(alarm.uuid)
            if alarm.alarm_message is not None:
                agent.inbox.append(alarm.alarm_message)

    def subscribe(self, uuid, topic):
        """ subscribe lets the Agent react to SubscribeMessage and adds the subscriber.
        to registered subscribers. Used by default during `_setup` by all agents.
        :param uuid:
        :param topic:
        :return:

        Notes: The method adds agent to subscriber list.
        Any agent may subscribe for the same topic many times (this is managed)
        """
        assert uuid in self.agents, "uuid not in scheduler."
        if topic not in self.mailing_lists:
            self.mailing_lists[topic] = set()
            self.log(level=DEBUG, msg="%s requesting topics added: %s" % (uuid, topic))
        if uuid not in self.mailing_lists[topic]:
            self.mailing_lists[topic].add(uuid)
            if topic == uuid:
                self.log(level=DEBUG, msg="%s subscribing to messages for itself." % (uuid))
            else:
                self.log(level=DEBUG, msg="%s subscribing to topic: %s" % (uuid, topic))
        else:
            self.log(level=DEBUG, msg="%s already subscribing to topic: %s" % (uuid, topic))

    def unsubscribe(self, uuid, topic=None):
        """ unsubscribes a subscriber from messages.
        :param uuid: agent uuid
        :param topic: str, if None, all topics are unsubscribed from.
        """
        if topic is not None:
            self.mailing_lists[topic].remove(uuid)
            if len(self.mailing_lists[topic]) == 0:
                del self.mailing_lists[topic]
            return

        for topic in [t for t in self.mailing_lists.keys()]:
            self.mailing_lists[topic].discard(uuid)
            if len(self.mailing_lists[topic]) == 0:
                del self.mailing_lists[topic]

    def get_subscriber_list(self, topic):
        """ Returns the list of subscribers of a particular topic."""
        if topic in self.mailing_lists:
            return self.mailing_lists.get(topic).copy()
        return []

    def get_subscription_topics(self):
        """ Returns the list of subscription topics"""
        return [t for t in self.mailing_lists.keys()]


