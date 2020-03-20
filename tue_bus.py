#!/usr/bin/env python3

import argparse
import datetime
import json
import os
import re
import sys
from multiprocessing.pool import ThreadPool
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from bs4 import BeautifulSoup


def main():
    args = parse_cli_args()
    stop_ids = args.ids
    lines = args.lines
    if args.config:
        config_ids, config_lines = load_config(args.config)
        stop_ids += [i for i in config_ids if i not in stop_ids]
        lines += [i for i in config_lines if i not in lines]

    if stop_ids is None or len(stop_ids) == 0:
        print("No bus stop ids. Exit.", file=sys.stderr)
        exit(1)

    with ThreadPool() as p:
        bus_stops = p.map(get_bus_stop_data, stop_ids)

    for bus_stop in bus_stops:
        print_table(bus_stop, lines=lines)
        print("")


def load_config(file_name):
    """ Load a json config file.

    Parameters
    ----------
    file_name : str
        Path to the config file.

    Returns
    -------
    list of str
        List of the bus stop ids.
    list of str
        List of selected bus lines.
    """
    with open(file_name, "r") as infile:
        data = json.loads(infile.read())
    ids = data["ids"]
    lines = data["lines"]
    return (ids, lines)


def parse_cli_args():
    """ Parse arguments passed from the command line. 

    Returns
    -------
    namespace
        Command line arguments.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="*",
                        help="Ids of the busstops or a json config file.")
    parser.add_argument("-c", "--config", help="Json config file.")
    parser.add_argument("-l", "--lines", nargs="+", default=list([]),
                        help="Only display these lines.")
    args = parser.parse_args()
    return args


def get_bus_stop_data(stop_id):
    """ Get meta data and bus data about a stop.

    Parameters
    ----------
    stop_id : str
        Id of the bus stop to get data from.

    Returns
    -------
    dict 
        Dictionary containing the following information:
            "stop"      : name of the stop
            "id"        : id
            "plattform" : platform identified by the id
            "data"      : Bus information as returned by get_bus_list.
    """
    raw = download_table(stop_id)
    table = extract_data_table(raw)
    data = get_bus_list(table)
    bus_stops = BusStopResolver()
    bus_stop = bus_stops.resolve(stop_id)
    bus_stop["data"] = data
    return bus_stop


def print_table(bus_stop, lines=list([])):
    """ Print a nice table with bus_stop information.

    Parameters
    ----------
    bus_stop : dict
        Dictionary containing the following information:
            "stop"      : name of the stop
            "id"        : id
            "plattform" : platform identified by the id
            "data"      : Bus information as returned by get_bus_list.
    lines : list of str
        If any lines are in the list, only busses of these lines are printed.
    """
    name = bus_stop["stop"]
    platform = bus_stop["plattform"]
    stop_id = bus_stop["id"]
    data = bus_stop["data"]
    print("Bus stop : {}".format(name))
    print("Platform : {}".format(platform))
    print("Stop id  : {}".format(stop_id))
    for entry in data:
        line = entry[0]
        dest = entry[1]
        time = entry[2]
        if len(lines) > 0:
            if not line in lines:
                continue
        print("{:3s}   {:15s}   {:8s}".format(
            line,
            dest,
            time
        ))


def download_table(busstop_id):
    """ Obtain data from the webpage associated to the busstop.

    Paramters
    ---------
    busstop_id : str
        Id of the busstop.
    """
    url = "https://www.swtue.de/abfahrt.html?halt=" + busstop_id
    res = get_webpage(url)
    return res


def get_bus_list(table):
    """ Extract information from the html table.

    Parameters
    ----------
    table : bs4.element
        Table extracted with beautiful soup 4.

    Returns
    list of (str, str, str)
        A list of tuples containing 
        (bus line, destination, time till leave).
    """
    lines = table.findAll("td", {"class": "linie"})
    lines = [save_to_str(e) for e in lines]
    dest = table.findAll("td", {"class": "richtung"})
    dest = [save_to_str(e) for e in dest]
    time = table.findAll("td", {"class": "abfahrt"})
    time = [save_to_str(e) for e in time]
    data = [(l, d, t) for l, d, t in zip(lines, dest, time)]
    return data


def save_to_str(e):
    """ Get the contents from an element in a save way.

    In case the contents list is empty, return an empty string.

    Parameters
    ----------
    e : bs.element
        Element to get the first content entry from.

    Returns
    -------
    str
        First entry as string or empty string.
    """
    try:
        s = str(e.contents[0]).strip()
    except IndexError:
        s = ""
    return s


def get_webpage(url):
    """ Download webpage under url.

    Parameters
    ----------
    url : str
        Url to the webpage.

    Returns
    -------
    bs4.element
        Webpage parsed with beautiful soup.
    """
    try:
        html = urlopen(url)
    except HTTPError as e:
        print(e)
    except URLError:
        print("Server down or incorrect domain")
    else:
        res = BeautifulSoup(html.read(), "html5lib")
    return res


def extract_data_table(webpage):
    """ Extract the data table from the html page.

    Parameters
    ----------
    webpage : bs4.element
        Beautiful soup element containing the web page.

    Returns
    -------
    bs4.element
        Table with bus information.
    """
    table = webpage.find("div", {"id": "vdfimain"})
    return table


class BusStopResolver:
    """ A class to resolve bus stop ids for Tübingen.

    Data is loaded from a json file which was extraced
    from https://www.swtue.de/abfahrt.html.    
    """

    def __init__(self):
        """ Initialize by loading data from file. """
        self.load()

    def load(self):
        """ Load the data from the json file. """
        data_file = self.get_data_file_path()
        with open(data_file, "r") as infile:
            data = json.loads(infile.read())
        self.data = {d["id"]: d for d in data}

    def get_data_file_path(self):
        """ Construct the data file path.

        The file busstop_data.json should be in the same directory
        as this file.
        """
        file_path = os.path.abspath(__file__)
        file_dir = os.path.dirname(file_path)
        json_file = os.path.join(file_dir, "busstop_data.json")
        return json_file

    def resolve(self, id):
        """ Get data for a bus stop id.

        Parametes
        ---------
        id : str
            Id of the bus stop.

        Returns
        -------
        dict
            Dictionary containing: id, name and plattform.
        """
        return self.data[id]


if __name__ == "__main__":
    main()
