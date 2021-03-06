# Copyright (c) 2017 Microsoft Corporation.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
#  rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
#  TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# ===================================================================================================================
import sys
sys.path.append('../')
import tensorflow as tf
import numpy as np
import os
import sys
from BayesAgent import BayesAgent
from BadAgent import BadAgent
from argparse import ArgumentParser
from datetime import datetime
from os import path
from threading import Thread, active_count
from time import sleep

from malmopy.agent import RandomAgent
try:
    from malmopy.visualization.tensorboard import TensorboardVisualizer
    from malmopy.visualization.tensorboard.cntk import CntkConverter
except ImportError:
    print('Cannot import tensorboard, using ConsoleVisualizer.')
    from malmopy.visualization import ConsoleVisualizer

from common import parse_clients_args, visualize_training, ENV_AGENT_NAMES, ENV_TARGET_NAMES
from agent import PigChaseChallengeAgent, FocusedAgent
from environment import PigChaseEnvironment, PigChaseSymbolicStateBuilder

# Enforce path
sys.path.insert(0, os.getcwd())
sys.path.insert(1, os.path.join(os.path.pardir, os.getcwd()))

BASELINES_FOLDER = 'results/baselines/pig_chase/%s/%s'
EPOCH_SIZE = 100


def agent_factory(name, role, type, clients, max_epochs, logdir, visualizer):

    assert len(clients) >= 2, 'Not enough clients (need at least 2)'
    clients = parse_clients_args(clients)
    
    builder = PigChaseSymbolicStateBuilder()
    env = PigChaseEnvironment(clients, builder, role=role,
                              randomize_positions=True)

    if role == 0:
        agent = BadAgent(name)

        obs = env.reset()
        reward = 0
        agent_done = False

        while True:
            if env.done:
                obs = env.reset()

            # select an action
            action = agent.act(obs, reward, agent_done)
            # take a step
            obs, reward, agent_done = env.do(action)


    else:
        config = tf.ConfigProto(allow_soft_placement=True)
        config.gpu_options.allow_growth = True
        with tf.Session(config = config) as sess:
            agent = BayesAgent(name, ENV_TARGET_NAMES[0], 'Agent_1', True, sess)
            if not agent.save:
                sess.run(tf.global_variables_initializer()) 
                print "Initialize"
            
            obs = env.reset()
            agent.reset(obs)
            reward = 0
            agent_done = False
            viz_rewards = []
            avg = []
            max_training_steps = EPOCH_SIZE * max_epochs
            for step in range(1, max_training_steps+1):
        
                # check if env needs reset
                if env.done:
                    avg.append(sum(viz_rewards))
                    visualize_training(visualizer, step, viz_rewards)
                    viz_rewards = []
                    obs = env.reset()
                    agent.reset(obs)
        
                # select an action
                action = agent.act(obs, reward, agent_done)
                # take a step
                obs, reward, agent_done = env.do(action)
                viz_rewards.append(reward)
        
            print "Average Reward: ", 1.*sum(avg)/len(avg)

def run_experiment(agents_def):
    assert len(agents_def) == 2, 'Not enough agents (required: 2, got: %d)'\
                % len(agents_def)

    processes = []
    for agent in agents_def:
        p = Thread(target=agent_factory, kwargs=agent)
        p.daemon = True
        p.start()

        # Give the server time to start
        if agent['role'] == 0:
            sleep(1)

        processes.append(p)

    try:
        # wait until only the challenge agent is left
        while active_count() > 2:
            sleep(0.1)
    except KeyboardInterrupt:
        print('Caught control-c - shutting down.')


if __name__ == '__main__':
    arg_parser = ArgumentParser('Pig Chase baseline experiment')
    arg_parser.add_argument('-t', '--type', type=str, default='astar',
                            choices=['astar', 'random'],
                            help='The type of baseline to run.')
    arg_parser.add_argument('-e', '--epochs', type=int, default=5,
                            help='Number of epochs to run.')
    arg_parser.add_argument('clients', nargs='*',
                            default=['127.0.0.1:10000', '127.0.0.1:10001'],
                            help='Minecraft clients endpoints (ip(:port)?)+')
    args = arg_parser.parse_args()

    logdir = BASELINES_FOLDER % (args.type, datetime.utcnow().isoformat())
    if 'malmopy.visualization.tensorboard' in sys.modules:
        visualizer = TensorboardVisualizer()
        visualizer.initialize(logdir, None)
    else:
        visualizer = ConsoleVisualizer()

    agents = [{'name': agent, 'role': role, 'type': args.type,
               'clients': args.clients, 'max_epochs': args.epochs,
               'logdir': logdir, 'visualizer': visualizer}
              for role, agent in enumerate(ENV_AGENT_NAMES)]

    run_experiment(agents)

