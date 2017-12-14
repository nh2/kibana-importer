#!/usr/bin/env python3

# Imports a Kibana export.json file into Kibana, as created via the
# 'Export Everything' button.
# Aims to have the same behaviour as the 'Import' button next to it.

# Dependencies:
# * `requests`

import argparse
import asyncio
import functools
import json
import logging
import requests
import socket
import sys
import time


DEFAULT_KIBANA_BASE_URL = 'http://localhost:5601'


def wait_for_green_status(kibana_base_url):
  s = requests.session() # HTTP session for keep-alive

  while True:
    try:
      r = s.get(kibana_base_url + '/api/status')
      r.raise_for_status()
      status = r.json()['status']['overall']['state']
      if status == 'green':
        break
      logging.debug('Kibana status is not green (is: {}), retrying...'.format(status))
    except requests.exceptions.ConnectionError:
      logging.debug('Kibana is not reachable, retrying...')
    time.sleep(0.1)

def get_default_index(kibana_base_url):
  """Retrieve the default index from kibana."""
  try:
    s = requests.session() # HTTP session for keep-alive
    r = s.get(kibana_base_url + '/api/kibana/settings')
    r.raise_for_status()
    defidx = r.json()['settings']['defaultIndex']['userValue']
    logging.debug("Found current defaultIndex=" + defidx)
    return defidx
  except:
    return ""

def get_old_default_index(objs):
  """Assumption: all the saved searches and visualizations refer to the defaultIndex (eg, logstash-*)
then we can find out what its ID was by looking at the first one found."""
  for obj in objs:
    try:
      found = str(json.loads(obj["_source"]["kibanaSavedObjectMeta"]["searchSourceJSON"])["index"])
      logging.debug("Found old defaultIndex=" + found)
      return found
    except:
      pass
  return ""

def replace_id(obj, old, new):
  """Replace an id only in the stringified portion of the object"""
  try:
    str = obj["_source"]["kibanaSavedObjectMeta"]["searchSourceJSON"]
    obj["_source"]["kibanaSavedObjectMeta"]["searchSourceJSON"] = str.replace(old, new)
    return obj
  except:
    return obj

async def upload_kibana_saved_json(kibana_base_url, jsonArray):
  eventloop = asyncio.get_event_loop()

  s = requests.session() # HTTP session for keep-alive
  futures = []

  for obj in jsonArray:
    typ = obj['_type']
    if typ not in ['dashboard', 'search', 'visualization']:
      print('Ignoring unknown Kibana export type: {}'.format(typ), file=sys.stderr)
      continue
    else:
      # All `typ` cases we handle above happen to have _id and _source fields.
      id = obj['_id']

      print('Processing {}: {}'.format(typ, id))

      data = {'attributes': obj['_source']}
      headers = {'kbn-xsrf': 'anything'}

      post_fun = functools.partial(
        s.post,
        kibana_base_url + '/api/saved_objects/{}/{}?overwrite=true'.format(typ, id),
        json=data, headers=headers, stream=False)

      future = eventloop.run_in_executor(None, post_fun)
      futures.append(future)

  for response in await asyncio.gather(*futures):
    response.raise_for_status()


def compute_ids(objs):
  pass

def main():
  parser = argparse.ArgumentParser(
    description='Imports a Kibana export.json file into Kibana via its REST API.\n\nExample:\n  {} --json export.json --kibana-url {}'.format(sys.argv[0], DEFAULT_KIBANA_BASE_URL),
    epilog='This is Free Software under the MIT license.\nCopyright 2017 Niklas Hambuechen <mail@nh2.me>',
    formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('--json', metavar='export.json', type=argparse.FileType('r'), default=sys.stdin, help='The Kibana JSON export file to import')
  parser.add_argument('--kibana-url', metavar=DEFAULT_KIBANA_BASE_URL, type=str, default=DEFAULT_KIBANA_BASE_URL, help='Kibana base URL (default ' + DEFAULT_KIBANA_BASE_URL + ')')
  parser.add_argument('--wait', action='store_true', help='Wait indefinitely for Kibana port to up with status green')
  parser.add_argument('--fix-idx', action='store_true', help='Attempt to map old defaultIndex ID to the one in the running kibana.')
  parser.add_argument('-v', '--verbose', action='store_true', help='increase output verbosity')
  args = parser.parse_args()

  if args.verbose:
    logging.basicConfig(level=logging.DEBUG)

  # Load JSON file; it contains an array of objects, whose _type field
  # determines what it is and which endpoint we have to hit.
  jsonArray = json.load(args.json)

  if args.wait:
    wait_for_green_status(args.kibana_url)

  if args.fix_idx:
    newidx = get_default_index(args.kibana_url)
    oldidx = get_old_default_index(jsonArray)

    if (oldidx != "" and oldidx != ""):
      jsonArray = [replace_id(x, oldidx, newidx) for x in jsonArray]
    else:
      print ("Did not find old index. ID's will be broken.")

    asyncio.get_event_loop().run_until_complete(upload_kibana_saved_json(args.kibana_url, jsonArray))

if __name__ == '__main__':
  main()
