# Copyright 2011 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import fixed_size_dict
import os

from basename_ranker import BasenameRanker
from query_result import QueryResult
from trace_event import *

class QueryCache(object):
  """Cached query execution results."""
  def __init__(self):
    self.searches = fixed_size_dict.FixedSizeDict(256)

class Query(object):
  """Encapsulates all the options to Quickopen search system."""

  @staticmethod
  def from_kargs(args = [], kwargs = {}):
    """A wrapper for old mechanisms of implicitly constructing queries."""
    if len(args) == 1:
      if isinstance(args[0], Query):
        return args[0]
      else:
        return Query(*args, **kwargs)        
    else:
      return Query(*args, **kwargs)

  def __init__(self, text, max_hits = 100, exact_match = False, current_filename = None, open_filenames = []):
    self.text = text
    self.max_hits = max_hits
    self.exact_match = exact_match
    self.current_filename = current_filename
    self.open_filenames = open_filenames

  @staticmethod
  def from_dict(d):
    return Query(d["text"],
                 d["max_hits"],
                 d["exact_match"],
                 d["current_filename"],
                 d["open_filenames"])

  def as_dict(self):
    return {
      "text": self.text,
      "max_hits": self.max_hits,
      "exact_match": self.exact_match,
      "current_filename": self.current_filename,
      "open_filenames": self.open_filenames
      }


  @tracedmethod
  def execute(self, shard_manager, query_cache):
    """
    Searches the index given the provided query.

    args should be either a Query object, or arguments to the Query-object constructor.
    """
    if self.text == '':
      return QueryResult()

    assert self.max_hits >= 0

    qkey = self.text + "@%i" % self.max_hits
    if qkey in query_cache.searches:
      res = query_cache.searches[qkey]
    else:
      res = self.execute_nocache(shard_manager, query_cache)
      query_cache.searches[qkey] = res

    if self.exact_match:
      return res.query_for_exact_matches(self.text)

    return res

  def execute_nocache(self, shard_manager, query_cache):
    self.text = self.text
    slashIdx = self.text.rfind('/')
    if slashIdx != -1:
      dirpart = self.text[:slashIdx]
      basename_query = self.text[slashIdx+1:]
    else:
      dirpart = None
      basename_query = self.text

    truncated = False

    if len(basename_query):
      hits, truncated = shard_manager.search_basenames(basename_query, self.max_hits)
    else:
      if len(dirpart):
        hits = []
        hits.extend([(f, 1) for f in shard_manager.files])
      else:
        hits = []

    if dirpart:
      reshits = []
      lower_dirpart = dirpart.lower()
      for hit in hits:
        dirname = os.path.dirname(hit[0])
        lower_dirname = dirname.lower()
        if lower_dirname.endswith(lower_dirpart):
          reshits.append(hit)
      hits = reshits

    # do one final ranking on the total rank
    res = QueryResult(hits=hits, truncated=truncated)
    res.apply_global_rank_adjustment()
    return res.get_copy_with_max_hits(self.max_hits)
