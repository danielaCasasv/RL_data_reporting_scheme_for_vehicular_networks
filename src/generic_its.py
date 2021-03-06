#!/usr/bin/env python

from __future__ import division

import subprocess
import os
import logging
import sys
import tempfile
import math
import random
import time
import numpy as np

from k_shortest_paths import k_shortest_paths
from optparse import OptionParser

import sumo_mannager
import graph_mannager
import log_mannager
import traffic_mannager
import rsu_mannager

import traci
import sumolib

import ql_agent
import RL_utils
import communication_manager
              

def run(network, begin, end, interval, route_log, replication, radius):

    #---w
    #(alpha, gamma, epsilon, episodes, n_states, n_actions)

    agente = ql_agent.Qagent(0.9, 0.9, 0.9, RL_utils.num_episodes, RL_utils.n_states, RL_utils.n_actions)
    episode_rewards = []
    episode_messages = []
    

    #---w

    print("*****",traci.getVersion())
    logging.debug("Building road graph")         
    road_network_graph = graph_mannager.build_road_graph(network)
    
    logging.debug("Reading network file")
    net = sumolib.net.readNet(network)

    logging.debug("Reading RSU list")
    rsu_list = rsu_mannager.get_rsu_positions_list()

    logging.debug("Mapping edges within each RSU")
    rsu_list = rsu_mannager.get_edges_within_rsu_coverage(rsu_list, net, radius, road_network_graph)
    
    route_list = {}
    # buffered_paths = {}
    
    logging.debug("Running simulation now")    
    step = 1
    # The time at which the first re-routing will happen
    # The time at which a cycle for collecting travel time measurements begins
    travel_time_cycle_begin = interval
    
    

    #while step == 1 or traci.simulation.getMinExpectedNumber() > 0:

    #while step <= end:
    sim_init = time.time()
    for e in range(RL_utils.num_episodes):
        print("episode:",e)
        step_messages = []
        step_rewards = []
        for agent_step in range(RL_utils.num_steps):
            print("agent_step:",agent_step)
            step = 0
            for interval_step in range(RL_utils.reporting_interval):
                #logging.debug("Minimum expected number of vehicles: %d" % traci.simulation.getMinExpectedNumber())
                #init = time.time()
                traci.simulationStep()      
                logging.debug("Simulation time %d" % step)
                #print("step:",step, time.time()-init)  
                step += 1   

                #if step % 60 == 0:
                #   logging.debug("Updating travel time on roads at simulation time %d" % step)
                #    road_network_graph = traffic_mannager.update_traffic_on_roads(road_network_graph)
        

                #if step > begin and step <= end and step%interval == 0:    
                #if step >= travel_time_cycle_begin and travel_time_cycle_begin <= end and step%interval == 0:
                #    road_network_graph = traffic_mannager.update_traffic_on_roads(road_network_graph)
                #    logging.debug("Updating travel time on roads at simulation time %d" % step)
                    
                                 
                #---w
                #mean_reward, mean_response_time = traffic_mannager.reroute_vehicles(road_network_graph, rsu_list, radius, agente, interval)   
                    
            #Data Reporting:

            vehicle_list = traci.vehicle.getIDList()
            if agent_step == 0: #first state
                state = RL_utils.get_state(vehicle_list,road_network_graph)
                action = agente.take_action(state)

            #apply action:
            init = time.time()
            #action=0
            messages_counter = communication_manager.report_to_RSU(vehicle_list, action) #action = treshold
            print("**time report_to_RSU:",time.time()-init)
            step_messages.append(messages_counter)
            reward = RL_utils.get_reward(messages_counter)
            step_rewards.append(reward)

            if agent_step != RL_utils.num_steps-1: # if not end_state 
                init = time.time()
                next_state = RL_utils.get_state(vehicle_list,road_network_graph)
                print("**time state:",time.time()-init)
                next_action = agente.take_action(next_state)
                agente.updateQ(reward,state,action,next_state,next_action,False) 
            else:
                agente.updateQ(reward,state,action,None,None,True) 
                        
            state = next_state
            action = next_action
                        
            #-- w
        episode_messages.append(np.mean(step_messages))
        episode_rewards.append(np.mean(step_rewards))    
                

    
    print("episode_messages:",episode_messages)
    print("episode_rewards:",episode_rewards)

    time.sleep(10)
    logging.debug("Simulation finished")
    print "Simulation finished"
    traci.close()
    sys.stdout.flush()
    time.sleep(10)

    print("***total time:",time.time()-sim_init)
    #print("response_times:",response_times)
    
        
def start_simulation(sumo, scenario, network, begin, end, interval, output, summary, route_log, replication, radius):
    logging.debug("Finding unused port")
    
    unused_port_lock = sumo_mannager.UnusedPortLock()
    unused_port_lock.__enter__()
    remote_port = sumo_mannager.find_unused_port()
    
    logging.debug("Port %d was found" % remote_port)
    
    logging.debug("Starting SUMO as a server")
    # define step in ms
    # "--step-length", "0.001",
    sumo = subprocess.Popen([sumo, "-W", "-c", scenario, "--tripinfo-output", output, "--device.emissions.probability", "1.0", "--summary-output", summary,"--remote-port", str(remote_port)], stdout=sys.stdout, stderr=sys.stderr)    
    unused_port_lock.release()
            
    try:     
        traci.init(remote_port)    
        run(network, begin, end, interval, route_log, replication, float(radius))
    #except Exception, e:
    except Exception as e:	
        logging.exception("Something bad happened")
    finally:
        logging.exception("Terminating SUMO")  
        sumo_mannager.terminate_sumo(sumo)
        unused_port_lock.__exit__()
        
def main():
    # Option handling

    pred_list = {}

    parser = OptionParser()
    parser.add_option("-c", "--command", dest="command", default="sumo", help="The command used to run SUMO [default: %default]", metavar="COMMAND")
    parser.add_option("-s", "--scenario", dest="scenario", default="cologne.sumo.cfg", help="A SUMO configuration file [default: %default]", metavar="FILE")
    parser.add_option("-n", "--network", dest="network", default="network.net.xml", help="A SUMO network definition file [default: %default]", metavar="FILE")    
    parser.add_option("-b", "--begin", dest="begin", type="int", default=0, action="store", help="The simulation time (s) at which the re-routing begins [default: %default]", metavar="BEGIN")
    parser.add_option("-e", "--end", dest="end", type="int", default=RL_utils.end_sim_time, action="store", help="The simulation time (s) at which the re-routing ends [default: %default]", metavar="END")
    parser.add_option("-i", "--interval", dest="interval", type="int", default=600, action="store", help="The interval (s) of classification [default: %default]", metavar="INTERVAL")
    parser.add_option("-o", "--output", dest="output", default="reroute.xml", help="The XML file at which the output must be written [default: %default]", metavar="FILE")
    parser.add_option("-l", "--logfile", dest="logfile", default=os.path.join(tempfile.gettempdir(), "sumo-launchd.log"), help="log messages to logfile [default: %default]", metavar="FILE")
    parser.add_option("-m", "--summary", dest="summary", default="summary.xml", help="The XML file at which the summary output must be written [default: %default]", metavar="FILE")
    parser.add_option("-r", "--route-log", dest="route_log", default="route-log.txt", help="Log of the entire route of each vehicle [default: %default]", metavar="FILE")
    parser.add_option("-t", "--replication", dest="replication", default="1", help="number of replications [default: %default]", metavar="REPLICATION")
    parser.add_option("-a", "--radius", dest="radius", default="1", help="communication radius of each RSU [default: %default]", metavar="RADIUS")

    
    (options, args) = parser.parse_args()
    
    logging.basicConfig(filename=options.logfile, level=logging.DEBUG)
    logging.debug("Logging to %s" % options.logfile)
    
    if args:
        logging.warning("Superfluous command line arguments: \"%s\"" % " ".join(args))
        
    start_simulation(options.command, options.scenario, options.network, options.begin, options.end, options.interval, options.output, options.summary, options.route_log, options.replication, options.radius)
    
if __name__ == "__main__":
    main()    
    
