from maslite import Agent, AgentMessage, Scheduler, Clock, AlarmRegistry
import random
import time
import heapq
from math import inf


class TestMessage(AgentMessage):

    def __init__(self, sender, receiver, created_time, scheduled_alarm_time):
        super().__init__(sender, receiver)
        self.created_time = created_time
        self.scheduled_alarm_time = scheduled_alarm_time

    def __repr__(self):
        return f'from {self.sender} to {self.receiver}, created at {self.created_time}, scheduled alarm time {self.scheduled_alarm_time}'

    def __str__(self):
        return f'from {self.sender} to {self.receiver}, created at {self.created_time}, scheduled alarm time {self.scheduled_alarm_time}'


class TestAgent(Agent):

    agents = []
    total_number_of_alarms_set = 0

    def __init__(self, uuid):
        super().__init__(uuid=uuid)
        assert uuid not in TestAgent.agents, "cannot have duplicated uuid"
        TestAgent.agents.append(uuid)
        self.operations[TestMessage.__name__] = self.receive_test_message

    def update(self):
        while self.messages:
            msg = self.receive()
            operation = self.operations.get(msg.topic)
            operation(msg)

    def receive_test_message(self, msg):

        # print(TestAgent.number_of_updates)
        number_of_alarms = random.randint(0, 5)  # randomly decide how many alarm message to send, maximum 3, minimum 0
        for _ in range(number_of_alarms):
            agent_to_receive_alarm = TestAgent.agents[random.randint(0, len(TestAgent.agents) - 1)]
            alarm_time = random.randint(0, 100)  # randomly decide what the alarm time should be
            self.set_alarm(alarm_time, TestMessage(self.uuid, agent_to_receive_alarm,
                                                   self.time, alarm_time), ignore_alarm_if_idle=False)
            TestAgent.total_number_of_alarms_set += 1


class TestSimulationClock(Clock):

    def __init__(self, scheduler_api):
        super().__init__(scheduler_api)
        self._time = 0

    def release_alarm_messages(self):
        if self.alarm_time:
            timestamp = heapq.heappop(self.alarm_time)
            list_of_messages = []
            clients = self.clients_to_wake_up[timestamp]
            for client in clients:
                registry = self.registry[client]
                assert isinstance(registry, AlarmRegistry)
                list_of_messages.extend(registry.release_alarm(timestamp))

            self.scheduler_api.mail_queue.extend(list_of_messages)
            self.clients_to_wake_up.pop(timestamp, None)

    def set_alarm(self, delay, alarm_message, ignore_alarm_if_idle):
        """
        :param delay: time delay from Agent.time until wakeup.
        :param alarm_message: AgentMessage
        :param ignore_alarm_if_idle: boolean - scheduler will ignore alarm if no messages
        are exchanged.
        """
        assert isinstance(delay, (int, float))
        assert isinstance(alarm_message, AgentMessage)
        assert isinstance(ignore_alarm_if_idle, bool)
        wakeup_time = self.time + delay
        if ignore_alarm_if_idle is False:
            self.last_required_alarm = max(self.last_required_alarm, wakeup_time)

        if wakeup_time not in self.clients_to_wake_up:
            heapq.heappush(self.alarm_time, wakeup_time)  # smallest first!

        registry = self.registry.get(alarm_message.receiver, None)
        if registry is None:
            registry = AlarmRegistry(alarm_message.receiver)
            self.registry[alarm_message.receiver] = registry
        registry.set_alarm(wakeup_time, alarm_message)

        self.clients_to_wake_up[wakeup_time].add(alarm_message.receiver)

    def tick(self, limit=None):
        """
        :param limit: time to which the clock can tick
        """
        if self.scheduler_api.mail_queue:
            pass  # don't progress time, there are new messages to handle
        elif self.scheduler_api.needs_update:
            pass  # don't progress time, agents are updating.
        elif self.alarm_time:  # jump in time to the next alarm.
            if not limit:
                limit = inf
            self._time = min(self.alarm_time[0], limit)
        else:
            pass
        return


class TestScheduler(Scheduler):

    def __init__(self, logger=None, real_time=True):
        super().__init__(logger=None, real_time=True)
        self.clock = TestSimulationClock(scheduler_api=self)


def test_speed_benchmark(random_seed=20, number_of_agents=100, number_of_iterations=700):
    # set up experiment 1
    random.seed(random_seed)
    agents = [TestAgent(i) for i in range(1, number_of_agents + 1)]  # let us create 5 agents
    scheduler = Scheduler(real_time=False)  # remember the real_time !
    for agent in agents:
        scheduler.add(agent)
    agents[0].send(TestMessage(1, 1, 0, 0))  # let us prime agent A with a test message
    start = time.time()
    scheduler.run(iterations=number_of_iterations)
    end = time.time()
    cpu_time_exp_1 = end - start
    total_number_of_alarms_exp_1 = TestAgent.total_number_of_alarms_set
    # reset
    random.seed(random_seed)
    TestAgent.agents = []
    TestAgent.total_number_of_alarms_set = 0
    # set up experiment 2
    agents = [TestAgent(i) for i in range(1, number_of_agents + 1)]  # let us create 5 agents
    scheduler = TestScheduler(real_time=False)  # remember the real_time !
    for agent in agents:
        scheduler.add(agent)
    agents[0].send(TestMessage(1, 1, 0, 0))  # let us prime agent A with a test message
    start = time.time()
    scheduler.run(iterations=number_of_iterations)
    end = time.time()
    cpu_time_exp_2 = end - start
    total_number_of_alarms_exp_2 = TestAgent.total_number_of_alarms_set

    assert total_number_of_alarms_exp_2 == total_number_of_alarms_exp_1, 'Must be an apple to apple comparison'
    print(f'Experiment Parameters: random seed {random_seed}, \nTotal Number of Agents: {number_of_agents}, \n'
          f'Total Number of Iterations: {number_of_iterations}, \nTotal Number of Alarms: {total_number_of_alarms_exp_1}')
    print(f'total cpu run time for scheduler using list and insort: {cpu_time_exp_1}')
    print(f'total cpu run time for scheduler using heap: {cpu_time_exp_2}')
    if cpu_time_exp_2 > cpu_time_exp_1:
        print(f'scheduler using heap is {100 * round(cpu_time_exp_2/cpu_time_exp_1 - 1, 4)}% slower')
    else:
        print(f'scheduler using heap is {100 * round(1 - cpu_time_exp_2/cpu_time_exp_1, 4)}% faster')