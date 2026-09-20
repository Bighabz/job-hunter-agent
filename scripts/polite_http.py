"""Cached public JSON discovery with per-host pacing and persistent backoff.

Informed by Scrapling's concurrency, caching and Retry-After documentation.
No credentials, proxies, fingerprint changes or challenge solving.
"""
import email.utils
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def retry_seconds(value, now):
    try:
        return max(0,float(value))
    except (TypeError,ValueError):
        try:return max(0,email.utils.parsedate_to_datetime(value).timestamp()-now)
        except (TypeError,ValueError,OverflowError):return 0


class PoliteJson:
    def __init__(self, directory, ttl=14400, delay=1.0, opener=None, clock=None, sleep=None):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.ttl=ttl;self.delay=delay
        self.opener=opener or urllib.request.urlopen
        self.clock=clock or time.time;self.sleep=sleep or time.sleep
        self.lock=threading.Lock();self.hosts={};self.next_at={}

    def write(self,path,value):
        tmp=path.with_suffix(f'.{os.getpid()}.{threading.get_ident()}.tmp')
        tmp.write_text(json.dumps(value),encoding='utf-8');tmp.replace(path)

    def read(self,path):
        try:return json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError):return {}

    def get(self,url,headers=None,timeout=25):
        host=urlsplit(url).hostname
        if not host or urlsplit(url).scheme!='https' or host=='linkedin.com' or host.endswith('.linkedin.com'):
            raise ValueError('HTTPS external employer discovery only; LinkedIn disabled')
        cache=self.directory/(hashlib.sha256(url.encode()).hexdigest()+'.json')
        with self.lock:lock=self.hosts.setdefault(host,threading.Lock())
        with lock:
            now=self.clock();stored=self.read(cache)
            if stored.get('url')==url and now-stored.get('at',0)<self.ttl:
                return stored['data']
            cooldown=self.directory/('cooldown-'+hashlib.sha256(host.encode()).hexdigest()+'.json')
            block=self.read(cooldown)
            if block.get('until',0)>now:
                raise RuntimeError(f'{host}: cooldown until {block["until"]}')
            wait=self.next_at.get(host,0)-now
            if wait>0:self.sleep(wait)
            started=self.clock()
            request=urllib.request.Request(url,headers=headers or {})
            try:
                with self.opener(request,timeout=timeout) as r:
                    data=json.loads(r.read().decode('utf-8','replace'))
            except urllib.error.HTTPError as e:
                if e.code in (403,429,503):
                    seconds=max(3600,retry_seconds(e.headers.get('Retry-After') if e.headers else None,self.clock()))
                    self.write(cooldown,{'until':self.clock()+seconds,'status':e.code,'host':host})
                raise
            finally:
                latency=self.clock()-started
                self.next_at[host]=self.clock()+max(self.delay,min(30,latency))
            self.write(cache,{'url':url,'at':self.clock(),'data':data})
            return data


_client=None
_init_lock=threading.Lock()
def fetch_json_cached(url,headers=None,timeout=25):
    global _client
    with _init_lock:
        if _client is None:
            root=Path(os.environ.get('JOBHUNT_APPLICATIONS',str(Path(__file__).resolve().parent.parent/'applications')))
            _client=PoliteJson(root/'_public_json_cache')
    return _client.get(url,headers,timeout)
