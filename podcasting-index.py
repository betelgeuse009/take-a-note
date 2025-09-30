import argparse
from datetime import date
import hashlib
import json
import requests
import feedparser
import os
import time
from dotenv import load_dotenv

load_dotenv()
# create and parse our args
parser = argparse.ArgumentParser()
parser.add_argument(dest='search_query', type=str, help="Query to search podcastindex.org for")
args = parser.parse_args()

# setup some basic vars for the search api. 
# for more information, see https://api.podcastindex.org/developer_docs
api_key = os.getenv('API_KEY')
api_secret = os.getenv('API_SECRET')
if not api_key or not api_secret:
    raise ValueError("API keys not found. Please set them in .env")

query = args.search_query
url = "https://api.podcastindex.org/api/1.0/search/byterm?q=" + query

# uncomment these to make debugging easier.
# print ('api key: ' + api_key);
# print ('api secret: ' + api_secret);
# print ('query: ' + query);
# print ('url: ' + url);

# the api follows the Amazon style authentication
# see https://docs.aws.amazon.com/AmazonS3/latest/dev/S3_Authentication2.html

# we'll need the unix time
epoch_time = int(time.time())

# our hash here is the api key + secret + time 
data_to_hash = api_key + api_secret + str(epoch_time)
# which is then sha-1'd
sha_1 = hashlib.sha1(data_to_hash.encode()).hexdigest()

# now we build our request headers
headers = {
    'X-Auth-Date': str(epoch_time),
    'X-Auth-Key': api_key,
    'Authorization': sha_1,
    'User-Agent': 'postcasting-index-python-cli'
}

# perform the actual post request
r = requests.post(url, headers=headers)

# if it's successful, dump the contents (in a prettified json-format)
# else, dump the error code we received
if r.status_code == 200:
    data = r.json()
    feeds = data.get("feeds", [])
    if feeds:
        # Loop through results and show feed + episodes
        for feed_data in feeds:
            rss_feed = feed_data["url"]
            print("RSS Feed:", rss_feed)

            # parse episodes
            parsed = feedparser.parse(rss_feed)
            if not parsed.entries:
                print("No episodes found.")
                continue
            print("\nAvaliable episodes:")
            for i , entry in enumerate(parsed.entries[:10],1):
                print(f"{i}. {entry.title}")
            choice = int(input("\nEnter episode number to download: "))-1
            if 0<= choice < len(parsed.entries):
                entry = parsed.entries[choice]
                audio_url = entry.enclosures[0].href if entry.enclosures else None
                if audio_url:
                    filename = os.path.basename(audio_url.split("?")[0])
                    print(f"Downloading: {entry.title} -> {filename}")
                    
                    with requests.get(audio_url,stream=True) as resp:
                        resp.raise_for_status()
                        with open(filename,"wb") as f:
                            for chunk in resp.iter_content(chunk_size=8192):
                                f.write(chunk)
                    print("Downloaded: ",filename)
                    break
                else:
                    print("No audio found!")
            else:
                print("Invalid choice!")
    else:
        print("No feeds found.")
else:
    print("Error:", r.status_code, r.text)

