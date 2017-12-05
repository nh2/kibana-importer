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
import requests
import sys


DEFAULT_KIBANA_BASE_URL = 'http://localhost:5601'


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


def main():
  parser = argparse.ArgumentParser(
    description='Imports a Kibana export.json file into Kibana via its REST API.\n\nExample:\n  {} --json export.json --kibana-url {}'.format(sys.argv[0], DEFAULT_KIBANA_BASE_URL),
    epilog='This is Free Software under the MIT license.\nCopyright 2017 Niklas Hambuechen <mail@nh2.me>',
    formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('--json', metavar='export.json', type=argparse.FileType('r'), default=sys.stdin, help='The Kibana JSON export file to import')
  parser.add_argument('--kibana-url', metavar=DEFAULT_KIBANA_BASE_URL, type=str, default=DEFAULT_KIBANA_BASE_URL, help='Kibana base URL (default ' + DEFAULT_KIBANA_BASE_URL + ')')
  args = parser.parse_args()

  # Load JSON file; it contains an array of objects, whose _type field
  # determines what it is and which endpoint we have to hit.
  jsonArray = json.load(args.json)

  asyncio.get_event_loop().run_until_complete(upload_kibana_saved_json(args.kibana_url, jsonArray))


if __name__ == '__main__':
  main()
