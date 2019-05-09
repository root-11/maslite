[![Build Status](https://travis-ci.org/root-11/maslite.svg?branch=master)](https://travis-ci.org/root-/maslite.svg?branch=master)


# MASlite
A multi-agent platform contrived by [Bjorn Madsen](https://uk.linkedin.com/in/bmadsen)

All right reserved &copy; 2016-2019. All code has been written by the author in 
isolation and any similarity to other systems is purely coincidental.

--------------

#### MASlite explained in 60 seconds:

MASlite is a simle python module for creating multi-agent simulations.

- _Simple_ API: Only 3 modules to learn: Scheduler, Agent & Agent message
- _Fast_: Handles up to 270 million messages per second
- _Lightweight_: 52kB.

It only has 3 components:

- The scheduler (main loop)
  - handles pause and proceed with a single call.
  - assures repeatability in execution, which makes agents easy to debug.
  - handles up to 270 million messages per second.

- Agent's 

  - are python classes that have setup(), update() and teardown() methods that can be customized. 
  - can exchange messages using send() and receive().
  - can subscribe/unsubscribe to message classes.
  - have clocks and can set alarms.
  - can be tested individually.
  - can have independent I/O/Database interaction.
  
- Messages
  - that have sender and receiver enable direct communication
  - that have topics and no receiver are treated as broadcasts, and sent to subscribers.
  
The are plenty of use-cases for MASlite:

- Prototyping MASSIVE&trade; type games.
- Creating data processing pipeline
- Optimisation Engine, for:
  - Scheduling (using Bjorn Madsen's distributed scheduling method)
  - Auctions (using Dimtry Bertsekas alternating iterative auction)
 
-------------------

All the user needs to worry about are the protocols of interaction, 
which conveniently may be summarised as:

1. Design the messages that an agent will send or receive as regular 
python objects that inherit the necessary implementation details from 
a basic `AgentMessage`. The messages must have an unambiguous `topic`.
2. Write the functions that are supposed to execute once an agent 
 receives one of the messages.
3. Update the agents operations (`self.operations`) with a dictionary
that describes the relationship between `topic` and `function`.
4. Write the update function that maintains the inner state of the agent
using `send` to send messages, and using `receive` to get messages.

The user can thereby create an agent using just:

    class HelloMessage(AgentMessage):
        def __init__(self, sender, receiver)
            super().__init__(sender=sender, receiver=receiver)
    
    
    class myAgent(Agent):
        def __init__(self):
            super().__init__()
            self.operations.update({HelloMessage.__name__: self.hello})
        
        def update(self):
            while self.messages:
                msg = self.receive()
                operation = self.operations.get(msg.topic))
                if operation is not None:
                    operation(msg)
                else:
                    self.logger.debug("%s: don't know what to do with: %s" % (self.uuid), str(msg)))
                    
        def hello(self, msg)
            print(msg)


That simple!

The dictionary `self.operations` which is inherited from the `Agent`-class
is updated with `{HelloMessage.__name__: self.hello}`. `self.operations` thereby acts 
as a pointer for when a `HelloMessage` arrives, so when the agents 
update function is called, it will get the topic from the message's and 
point to the function `self.hello`, where `self.hello` in this simple
example just prints the content of the message. 

More nuanced behaviour, can also be embedded without the user having
to worry about any externals. For example if some messages take 
precedence over others (priority messages), the inbox should be emptied 
in the beginning of the update function for sorting. 

Here is an example where some topics are treated with priority over 
others:

    class AgentWithPriorityInbox(Agent):
        def __init__(self):
            super().__init__()
            self.operations.update({"1": self.some_priority_function, 
                                    "2": self.some_function, 
                                    "3": self.some_function,  # Same function for 2 topics.! 
                                    "hello": self.hello, })
            self.priority_topics = ["1","2","3"]
            self.priority_messages = deque()  # from collections import deque
            self.normal_messages = deque()    # deques append and popleft are threadsafe.
    
        def update(self):
            # 1. Empty the inbox and sort the messages using the topic:
            while self.messages:
                msg = self.receive()
                if msg.topic in self.priority_topics:
                    self.priority_messages.append(msg)
                else:
                    self.normal_messages.append(msg)
            
            # 2. We've now sorted the incoming messages and can now extend
            # the priority message deque with the normal messages:
            self.priority_messages.extend(normal_messages)
            
            # 3. Next we process them as usual:
            while len(self.priority_messages) > 0:
                msg = self.priority_messages.popleft()
                operation = self.operations.get(msg.topic)
                if operation is not None:
                    operation(msg)
                else:
                    ...

The only thing which the user needs to worry about, is that the update
function cannot depend on any externals. The agent is confined to
sending (`self.send(msg)`) and receiving (`msg = self.receive()`) 
messages which must be processed within the function `self.update`.
Any responses to sent messages will not happen until the agent runs
update again.

If any state needs to be stored within the agent, such as for example
memory of messages sent or received, then the agents `__init__` should
declare the variables as class variables and store the information.
Calls to databases, files, etc. can of course happen, including the usage
of `self.setup()` and `self.teardown()` which are called when the agent
is, respectively, started or stopped. See the boiler-plate (below) for a more 
detailed description. 
 
### Boilerplate

The following boiler-plate allows the user to manage the whole lifecycle
of an agent, including:

1. add variables to `__init__` which can store information between updates.
2. react to topics by extending `self.operations`
2. extend `setup` and `teardown` for start and end of the agents lifecycle.
4. use `update` with actions before(1), during(2) and after(3) reading messages.

There are no requirements, for using all functions. The boiler-plate merely
seeks to illustrate typical usage.

There are also no requirements for the agent to be programmed in procedural,
functional or object oriented manner. Doing that is completely up to the 
user of MASlite.

    class MyAgent(Agent):
        def __init__(self):
            super().__init__()
            # add variables here.
            
            # remember to register topics and their functions:
            self.operations.update({"topic x": self.x,
                                    "topic y": self.y,
                                    "topic ...": self....})
        
        def setup(self):
            # add own setup operations here.
            
            # register topics with the mailman..!
            # naive:
            for topic in self.operations.keys():
                self.subscribe(topic)
            # selective
            for topic in ["topic x","topic y","topic ..."]:
                self.subscribe(topic)
        
        def teardown(self):
            # add own teardown operations here.
            
        def update(self):
            # do something before reading messages
            self.action_before_processing_messages()
        
            # read the messages
            while self.messages:
                msg = self.receive()
                
                # react immediately to some messages:
                operation = self.operations.get(msg.topic)
                if operation is not None:
                    operation(msg)
            
            # react after reading all messages:
            self.action_after_processing_all_messages()
        
        # Functions added by the user that are not inherited from the 
        # `Agent`-class. If the `update` function should react on these,
        # the topic of the message must be in the self.operations dict.
        
        def action_before_processing_messages(self)
            # do something.
            
        def action_after_processing_all_messages(self)
            # do something. Perhaps send a message to somebody that update is done?
            msg = DoneMessages(sender=self, receiver=SomeOtherAgent)
            self.send(msg)
        
        def x(msg):
            # read msg and send a response
            from_ = msg.sender
            response = SomeMessage(sender=self, receiver=from_) 
            self.send(response)
        
        def y(msg):
            # ...
        

### Messages

Messages are objects and are required to use the base class `AgentMessage`.

When agents receive messages they should be interpreted by their topic, which
should (by convention) also be the class name of the message. Practice has shown
that there are no obvious reasons where this convention shouldn't apply, so 
messages which don't have a topic declared explicitly inherit the class name. 
An example is shown below:

    >>> from maslite import AgentMessage
    >>> class MyMsg(AgentMessage):
    ...     def __init__(sender, receiver):
    ...         super().__init__(sender=sender, receiver=receiver)
    ...
    
    >>> m = MyMsg(sender=1, receiver=2)
    >>> m.topic
    
    'MyMsg'

Adding functions to messages. Below is an example of a message with it's own
function(s): 

    class DatabaseUpdateMessage(AgentMessage):
        """ Description of the message """
        def __init__(self, sender, senders_db_alias):
            super().__init__(sender=sender, receiver=DatabaseAgent.__name__)
            self.senders_db_alias
            self._states = {1: 'new', 2: 'read'} 
            self._state = 1
            
        def get_senders_alias(self):
            return self.senders_db_alias
            
        def __next__(self)
            if self._state + 1 <= max(self._states.keys()):
                self._state += 1
        
        def state(self):
            return self._states[self._state]

The class `DatabaseUpdateMessage` is subclassed from the `AgentMessage` so that the basic message
handling properties are available for the DatabaseUpdateMessage. This helps the user as s/he doesn't
need to know anything about how the message handling system works.

The init function requires a sender, which normally defaults to the agent's `self`.
The `AgentMessage` knows that if it gets an agent in it's `__init__` call, it will
obtain the agents UUID and use that. Similar applies to a receiver, where the typical
operation is based on that the local agent gets a message from the sender and only 
knows the sender based on msg.get_sender() which returns the sending agents UUID. 
If the sender might change UUID, in the course of multiple runs, the local agent 
should be instructed to use, for example, the `senders_db_alias`. For the purpose
of illustration, the message above contains the function `get_senders_alias` which
then can be persistent over multiple runs.

The message is also designed to be returned to save pythons garbage collector:
When the DatabaseAgent receives the message, the `__next__`-function allows the
agent to call `next(msg)` to progress it's `self._state` from '1' (new) to '2' (read)
before returning it to the sender using 'self.send(msg)'. In such case it is 
important that the DatabaseAgent doesn't store the message in its variables, as
the message must __not__ have any open object pointers when sent. This is due to
multiprocessing which uses `multiprocessing.queue`s for exchanging messages, which
require that `Agent`s and `AgentMessage`s can be pickled.

If an `Agent` can't be pickled when added to the `Scheduler`, the scheduler will
raise an error explaining that the are open pointer references. Messages are a 
bit more tolerant as the `mailman` that manages the messages will try to send
the message and hope that the shared pointer will not cause conflicts. If sharing
of object pointers is required by the user (for example during prototyping) the 
scheduler must be set up with `number_of_multiprocessors=0` which forces the 
scheduler to run single-process-single-threaded. 


__Message Conventions__:

* Messages which have `None` as receiver are considered broadcasts. The logic is 
that if you don't know who exactly you are sending it to, send it it to `None`, and
you might get a response if any other agent react on the topic of the message.
The magic behind the scenes is handled by the schedulers mailmanager (`mailman`) 
which keeps track of all topics that any `Agent` subscribes to. 
By convention the topic of the message should be `self.__class__.__name__`.

* Messages which have a `class.__name__` as receiver, will be received by all agents
of that class.

* Messages which have a particular UUID as receiver, will be received by the agent 
holding that UUID. If anyone other agent is tracking that UUID, by subscribing to
it, then the tracking agent will receive a `deepcopy` of the message, and not the 
original. 

* To get the UUID of the sender the method `msg.sender` is available.

* To subscribe/unsubscribe to messages the agents should use the `subscribe`
function directly.

These methods are run when the agent is added (`setup`) to, or removed from (`teardown`), the 
scheduler. The internal operation of the agents `run` method guarantees this:

    def run(self):
        """ The main operation of the Agent. """
        if not self.is_setup():
            self.setup()
        if not self._quit:
            self.update()
        if self._quit:
            self.teardown()

The can extend the setup methods either by writing their own `self.setup`-method 
(_recommended approach_).


### How to load data from a database connection 

When agents are added to the scheduler `setup` is run.
When agents are removed from MASlite `teardown` is run.

if agents are added and removed iteratively, they will load their 
state during `setup` and store it during `teardown` from some database. 
It is not necessary to let the scheduler know where the database is. 
The agents can keep track of this themselves. 

Though the user might find it attractice to use  `uuid` to identify,
a particular `Agent` the user should keep 
in mind that the UUID is unique with __every__ creation and destruction 
of the agent. To expect or rely on the UUID to be persistent would lead 
to logical fallacy.

The user must use`setup` and `teardown` and include a naming convention 
that assures that the agent doesn't depend on the UUID. For example:

    # get the data from the previously stored agent
    begin transaction:
        id = SELECT agent_id FROM stored_agents WHERE agent_alive == False LIMIT 1;
        UPDATE stored_agents WHERE agent_id == id VALUES (agent_live = TRUE);
        properties = SELECT * FROM stored_agents WHERE agent_id == id;
    end transaction;
    # Finally let the agent load the properties:
    self.load(properties) 

An approach such as above assures that the agent that is revived has no 
dependency to the UUID.

### Getting started

To get started only 3 steps are required:

Step 1. setup a scheduler

    >>> from maslite import Agent, Scheduler
    >>> s = Scheduler(number_of_multi_processors=0)
    
Step 2. create agents which have `setup`, `teardown` and `update` methods.

    >>> class MyAgent(Agent):
    ...     def __init__(self):
    ...         super().__init__()
    ...     def setup(self):
    ...         pass
    ...     def teardown(self):
    ...         pass
    ...     def update(self):
    ...         pass
        
    >>> m = MyAgent()
    >>> s.add(m)
    2017-02-11 15:05:27,171 - DEBUG - Registering agent MyAgent 331228774898081874557512062996431768652

Step 3. run the scheduler (nothing happens here)

    >>> s.run(pause_if_idle=True)
    2017-02-11 15:09:20,120 - DEBUG - Pausing Scheduler, use 'run()' to continue. Use 'stop()' to shutdown remote processors.

Other methods such as `s.run(seconds=None, iterations=None, 
pause_if_idle=False)` can be applied as the user,
finds it suitable.

Step 4. call the schedulers `stop` method to gracefully execute the `teardown` method
on all agents as a part of the shutdown procedure.

    >>> s.stop()
    2017-02-11 15:09:37,055 - DEBUG - Scheduler shutdown complete.


### Debugging with pdb or breakpoints (PyCharm)

Debugging is easily performed by putting breakpoint at the beginning of
the update function. In that way you can watch what happens inside the 
agent during its state-update.

### Typical mistakes

The user constructs the agent correctly with:
 
1. the methods `update`, `send`, `receive`, `setup` and `teardown`,
2. adding the agent to the scheduler using `scheduler.add(agent)`.
3. runs the scheduler using `scheduler.run()`, 

...but... 

Q: The agents don't seem to update?

A: The agents are not getting any messages and are therefore not updated.
This is correct behaviour, as `update` only should run when there are
new messages! 
To force agents to run `update` in every scheduling cycle, use the hidden 
method: `agent.keep_awake=True`. Doing this blindly however is a poor design
choice if the agent merely is polling for data. For this purpose 
`agent.set_alarm_clock(agent.now()+1)` should be used, as this allows the
agent to sleep for 1 second and the be "woken up" by the alarm message.

The reason it is recommended to use the alarm instead of setting 
`keep_awake=True` is that the workload of the system remains transparent 
at the level of message exchange. Remember that the internal state of 
the agents should always be hidden whilst the  messages should be 
indicative of any activity. 

### Adjust runspeed using the clock.

The clock is a powertool in MASlite that should be studied. 
The clock has the ability to:

* run at speeds `-inf`; `+inf` and any floating point progressing in between. 

* start at time `-inf`; `+inf` and any floating point time in between.

The clock is set using the api calls to the clock:

    >>> s = Scheduler()
    2017-02-11 15:15:00,197 - INFO - Scheduler is running with uuid: 206586991924651126011034509456004484857
    2017-02-11 15:15:00,197 - DEBUG - Registering agent Clock 237028863335333747268219642853960174161
    2017-02-11 15:15:00,197 - DEBUG - Registering agent MailMan 108593288939288121173991719827939198422
    >>> s.now()
    0
    >>> s.clock.time = 1000
    >>> s.now()
    1000
    >>> s.run(seconds=5)
    2017-02-11 15:16:49,395 - DEBUG - Pausing Scheduler, use 'run()' to continue. Use 'stop()' to shutdown remote processors.
    >>> s.now()
    1005
    >>> s.clock.clock_speed = 200
    >>> s.now()
    1005
    >>> s.run(seconds=5)
    2017-02-11 15:17:41,355 - DEBUG - Pausing Scheduler, use 'run()' to continue. Use 'stop()' to shutdown remote processors.
    >>> s.now()
    2005
    >>> s.now()
    2005
    

In the calls (above) the scheduler first sets the time to `1000` (whatever that is).
using `s.clock.time`. Next it sets the clock speed using `s.clock.clock_speed`
to 200 times real-time


1. `clock.time = `__time in seconds__. Typically time is set to time since 1970-01-01T00:00:00.000000 - the UNIX epoch - using `time.time()`
2. `clock.clock_speed = 1.000000`

If the clock is set to run with `clock.clock_speed = None`, the scheduler
will ask the clock to progress in jumps, so which behaves like follows: (pseudo code):

    if Clock.clock_speed is None:
        if not mailman.messages:
            if self.pending_tasks() == 0:
                Ask clock to set time to the time of the next event.
            else: wait for multiprocessor to return computed agent.
        else: continue until no new messages
    else: continue clock as normal.

To adjust the timing during a simulation (for whatever reason), the 
scheduler should be primed with messages:

1. run at maximum speed: `self.set_new_clock_speed_as_timed_event(start_time=now(), speed=None)`
2. set clock to 10x speed 1 hour into the simulation: `set_runtime(start_time=now()+1*60*60, speed=10)` This will take 6 minutes in real-time.
3. set the clock to 1x (real-time) speed 3 hours into the simulation: `set_runtime(start_time=now()+3*60*60, speed=1)` This will take 1 hour in real time.
4. set clock to 10x speed 4 hour into the simulation: `set_runtime(start_time=now()+4*60*60, speed=10)`
5. set the clock to 'None' to run as fast as possible for the rest of the simulation: `set_runtime(start_time=now()+6*60*60, speed=None)`

Note: The clock_speed can be set as an argument in the schedulers `run` function:

    Scheduler.run(seconds=None, iterations=None, pause_if_idle=False,
                  clock_speed=1.0)

...

### Loadbalancing.

MASlite only makes one assumption: That it's the primary service on the
hardware where it is running. 

### MASlite running on multiple machines 

Not implemented yet.

### API access to every agent 

Not implemented yet.

