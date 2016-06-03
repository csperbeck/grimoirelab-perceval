#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2016 Bitergia
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# Authors:
#     Santiago Dueñas <sduenas@bitergia.com>
#     Alvaro del Castillo <acs@bitergia.com>
#

import argparse
import datetime
import json
import shutil
import sys
import tempfile
import unittest

import httpretty

if not '..' in sys.path:
    sys.path.insert(0, '..')

from perceval.cache import Cache
from perceval.errors import CacheError
from perceval.backends.discourse import Discourse, DiscourseCommand, DiscourseClient


DISCOURSE_SERVER_URL = 'http://example.com'
DISCOURSE_TOPICS_URL = DISCOURSE_SERVER_URL + '/latest.json'
DISCOURSE_TOPIC_URL_1148 = DISCOURSE_SERVER_URL + '/t/1148.json'
DISCOURSE_TOPIC_URL_1149 = DISCOURSE_SERVER_URL + '/t/1149.json'
DISCOURSE_POST_URL_1 = DISCOURSE_SERVER_URL + '/posts/21.json'
DISCOURSE_POST_URL_2 = DISCOURSE_SERVER_URL + '/posts/22.json'


def read_file(filename, mode='r'):
    with open(filename, mode) as f:
        content = f.read()
    return content


class TestDiscourseBackend(unittest.TestCase):
    """Discourse backend tests"""

    def test_initialization(self):
        """Test whether attributes are initializated"""

        discourse = Discourse(DISCOURSE_SERVER_URL, origin='test')

        self.assertEqual(discourse.url, DISCOURSE_SERVER_URL)
        self.assertEqual(discourse.origin, 'test')
        self.assertIsInstance(discourse.client, DiscourseClient)

        # When origin is empty or None it will be set to
        # the value in url
        discourse = Discourse(DISCOURSE_SERVER_URL)
        self.assertEqual(discourse.url, DISCOURSE_SERVER_URL)
        self.assertEqual(discourse.origin, DISCOURSE_SERVER_URL)

        discourse = Discourse(DISCOURSE_SERVER_URL, origin='')
        self.assertEqual(discourse.url, DISCOURSE_SERVER_URL)
        self.assertEqual(discourse.origin, DISCOURSE_SERVER_URL)

    @httpretty.activate
    def test_fetch(self):
        """Test whether a list of topics is returned"""

        requests_http = []

        bodies_topics = [read_file('data/discourse_topics.json'),
                         read_file('data/discourse_topics_empty.json')]
        body_topic_1148 = read_file('data/discourse_topic_1148.json')
        body_topic_1149 = read_file('data/discourse_topic_1149.json')
        body_post = read_file('data/discourse_post.json')

        def request_callback(method, uri, headers):
            if uri.startswith(DISCOURSE_TOPICS_URL):
                body = bodies_topics.pop(0)
            elif uri.startswith(DISCOURSE_TOPIC_URL_1148):
                body = body_topic_1148
            elif uri.startswith(DISCOURSE_TOPIC_URL_1149):
                body = body_topic_1149
            elif uri.startswith(DISCOURSE_POST_URL_1) or \
                 uri.startswith(DISCOURSE_POST_URL_2):
                body = body_post
            else:
                raise

            requests_http.append(httpretty.last_request())

            return (200, headers, body)

        httpretty.register_uri(httpretty.GET,
                               DISCOURSE_TOPICS_URL,
                               responses=[
                                    httpretty.Response(body=request_callback) \
                                    for _ in range(2)
                               ])
        httpretty.register_uri(httpretty.GET,
                               DISCOURSE_TOPIC_URL_1148,
                               responses=[
                                    httpretty.Response(body=request_callback)
                               ])
        httpretty.register_uri(httpretty.GET,
                               DISCOURSE_TOPIC_URL_1149,
                               responses=[
                                    httpretty.Response(body=request_callback)
                               ])
        httpretty.register_uri(httpretty.GET,
                               DISCOURSE_POST_URL_1,
                               responses=[
                                    httpretty.Response(body=request_callback)
                               ])
        httpretty.register_uri(httpretty.GET,
                               DISCOURSE_POST_URL_2,
                               responses=[
                                    httpretty.Response(body=request_callback)
                               ])

        # Test fetch topics
        discourse = Discourse(DISCOURSE_SERVER_URL)
        topics = [topic for topic in discourse.fetch()]

        self.assertEqual(len(topics), 2)

        # Topics are returned in reverse order
        # from oldest to newest
        self.assertEqual(topics[0]['data']['id'], 1149)
        self.assertEqual(len(topics[0]['data']['post_stream']['posts']), 2)
        self.assertEqual(topics[0]['origin'], DISCOURSE_SERVER_URL)
        self.assertEqual(topics[0]['uuid'], '18068b95de1323a84c8e11dee8f46fd137f10c86')
        self.assertEqual(topics[0]['updated_on'], 1464134770.909)

        self.assertEqual(topics[1]['data']['id'], 1148)
        self.assertEqual(topics[1]['origin'], DISCOURSE_SERVER_URL)
        self.assertEqual(topics[1]['uuid'], '5298e4e8383c3f73c9fa7c9599779cbe987a48e4')
        self.assertEqual(topics[1]['updated_on'], 1464144769.526)

        # The next assertions check the cases whether the chunk_size is
        # less than the number of posts of a topic
        self.assertEqual(len(topics[1]['data']['post_stream']['posts']), 22)
        self.assertEqual(topics[1]['data']['post_stream']['posts'][0]['id'], 18952)
        self.assertEqual(topics[1]['data']['post_stream']['posts'][20]['id'], 2500)

        # Check requests
        expected = [{
                     'page' : ['0']
                    },
                    {
                     'page' : ['1']
                    },
                    {},
                    {},
                    {},
                    {}]

        self.assertEqual(len(requests_http), len(expected))

        for i in range(len(expected)):
            self.assertDictEqual(requests_http[i].querystring, expected[i])

    @httpretty.activate
    def test_fetch_from_date(self):
        """Test whether a list of topics is returned from a given date"""

        requests_http = []

        bodies_topics = [read_file('data/discourse_topics.json'),
                         read_file('data/discourse_topics_empty.json')]
        body_topic_1148 = read_file('data/discourse_topic_1148.json')
        body_topic_1149 = read_file('data/discourse_topic_1149.json')
        body_post = read_file('data/discourse_post.json')

        def request_callback(method, uri, headers):
            if uri.startswith(DISCOURSE_TOPICS_URL):
                body = bodies_topics.pop(0)
            elif uri.startswith(DISCOURSE_TOPIC_URL_1148):
                body = body_topic_1148
            elif uri.startswith(DISCOURSE_TOPIC_URL_1149):
                body = body_topic_1149
            elif uri.startswith(DISCOURSE_POST_URL_1) or \
                 uri.startswith(DISCOURSE_POST_URL_2):
                body = body_post
            else:
                raise

            requests_http.append(httpretty.last_request())

            return (200, headers, body)

        httpretty.register_uri(httpretty.GET,
                               DISCOURSE_TOPICS_URL,
                               responses=[
                                    httpretty.Response(body=request_callback) \
                                    for _ in range(2)
                               ])
        httpretty.register_uri(httpretty.GET,
                               DISCOURSE_TOPIC_URL_1148,
                               responses=[
                                    httpretty.Response(body=request_callback)
                               ])
        httpretty.register_uri(httpretty.GET,
                               DISCOURSE_TOPIC_URL_1149,
                               responses=[
                                    httpretty.Response(body=request_callback)
                               ])
        httpretty.register_uri(httpretty.GET,
                               DISCOURSE_POST_URL_1,
                               responses=[
                                    httpretty.Response(body=request_callback)
                               ])
        httpretty.register_uri(httpretty.GET,
                               DISCOURSE_POST_URL_2,
                               responses=[
                                    httpretty.Response(body=request_callback)
                               ])

        # On this tests only one topic will be retrieved
        from_date = datetime.datetime(2016, 5, 25, 2, 0, 0)

        discourse = Discourse(DISCOURSE_SERVER_URL)
        topics = [topic for topic in discourse.fetch(from_date=from_date)]

        self.assertEqual(len(topics), 1)

        self.assertEqual(topics[0]['data']['id'], 1148)
        self.assertEqual(len(topics[0]['data']['post_stream']['posts']), 22)
        self.assertEqual(topics[0]['origin'], DISCOURSE_SERVER_URL)
        self.assertEqual(topics[0]['uuid'], '5298e4e8383c3f73c9fa7c9599779cbe987a48e4')
        self.assertEqual(topics[0]['updated_on'], 1464144769.526)

        # Check requests
        expected = [{
                     'page' : ['0']
                    },
                    {},
                    {},
                    {}]

        self.assertEqual(len(requests_http), len(expected))

        for i in range(len(expected)):
            self.assertDictEqual(requests_http[i].querystring, expected[i])

    @httpretty.activate
    def test_fetch_empty(self):
        """Test whether it works when no topics are fetched"""

        body = read_file('data/discourse_topics_empty.json')
        httpretty.register_uri(httpretty.GET,
                               DISCOURSE_TOPICS_URL,
                               body=body, status=200)

        discourse = Discourse(DISCOURSE_SERVER_URL)
        topics = [topic for topic in discourse.fetch()]

        self.assertEqual(len(topics), 0)


class TestDiscourseBackendCache(unittest.TestCase):
    """Discourse backend tests using a cache"""

    def setUp(self):
        self.tmp_path = tempfile.mkdtemp(prefix='perceval_')

    def tearDown(self):
        shutil.rmtree(self.tmp_path)

    @httpretty.activate
    def test_fetch_from_cache(self):
        """Test whether the cache works"""

        bodies_topics = read_file('data/discourse_topics.json', mode='rb')
        bodies_posts_job = read_file('data/discourse_posts.json')

        def request_callback(method, uri, headers):
            if uri.startswith(DISCOURSE_POSTS_URL):
                body = bodies_topics
            elif uri.startswith(DISCOURSE_POSTS_TOPIC_URL_1) or \
                 uri.startswith(DISCOURSE_POSTS_TOPIC_URL_2):
                body = bodies_posts_job
            else:
                body = ''

            return (200, headers, body)

        httpretty.register_uri(httpretty.GET,
                               DISCOURSE_POSTS_URL,
                               responses=[
                                    httpretty.Response(body=request_callback) \
                                    for _ in range(3)
                               ])
        httpretty.register_uri(httpretty.GET,
                               DISCOURSE_POSTS_TOPIC_URL_1,
                               responses=[
                                    httpretty.Response(body=request_callback) \
                                    for _ in range(2)
                               ])
        httpretty.register_uri(httpretty.GET,
                               DISCOURSE_POSTS_TOPIC_URL_2,
                               responses=[
                                    httpretty.Response(body=request_callback) \
                                    for _ in range(2)
                               ])

        # First, we fetch the posts from the server, storing them
        # in a cache
        cache = Cache(self.tmp_path)
        discourse = Discourse(DISCOURSE_SERVER_URL, cache=cache)

        posts = [post for post in discourse.fetch()]

        # Now, we get the posts from the cache.
        # The contents should be the same and there won't be
        # any new request to the server
        cached_posts = [post for post in discourse.fetch_from_cache()]
        self.assertEqual(len(cached_posts), len(posts))

        with open("data/discourse_post.json") as post_json:
            first_post = json.load(post_json)
            self.assertDictEqual(cached_posts[0]['data'], first_post['data'])

    def test_fetch_from_empty_cache(self):
        """Test if there are not any posts returned when the cache is empty"""

        cache = Cache(self.tmp_path)
        discourse = Discourse(DISCOURSE_SERVER_URL, cache=cache)
        cached_posts = [post for post in discourse.fetch_from_cache()]
        self.assertEqual(len(cached_posts), 0)

    def test_fetch_from_non_set_cache(self):
        """Test if a error is raised when the cache was not set"""

        discourse = Discourse(DISCOURSE_SERVER_URL)

        with self.assertRaises(CacheError):
            _ = [post for post in discourse.fetch_from_cache()]


class TestDiscourseCommand(unittest.TestCase):
    """Tests for DiscourseCommand class"""

    @httpretty.activate
    def test_parsing_on_init(self):
        """Test if the class is initialized"""

        args = ['--origin', 'test', DISCOURSE_SERVER_URL]

        cmd = DiscourseCommand(*args)
        self.assertIsInstance(cmd.parsed_args, argparse.Namespace)
        self.assertEqual(cmd.parsed_args.url, DISCOURSE_SERVER_URL)
        self.assertEqual(cmd.parsed_args.origin, 'test')
        self.assertIsInstance(cmd.backend, Discourse)

    def test_argument_parser(self):
        """Test if it returns a argument parser object"""

        parser = DiscourseCommand.create_argument_parser()
        self.assertIsInstance(parser, argparse.ArgumentParser)


class TestDiscourseClient(unittest.TestCase):
    """Discourse API client tests.

    These tests do not check the body of the response, only if the call
    was well formed and if a response was obtained. Due to this, take
    into account that the body returned on each request might not
    match with the parameters from the request.
    """

    def test_init(self):
        """Test whether attributes are initializated"""

        client = DiscourseClient(DISCOURSE_SERVER_URL,
                                 api_key='aaaa')

        self.assertEqual(client.url, DISCOURSE_SERVER_URL)
        self.assertEqual(client.api_key, 'aaaa')

    @httpretty.activate
    def test_topics_page(self):
        """Test topics_page API call"""

        # Set up a mock HTTP server
        body = read_file('data/discourse_topics.json')
        httpretty.register_uri(httpretty.GET,
                               DISCOURSE_TOPICS_URL,
                               body=body, status=200)

        # Call API without args
        client = DiscourseClient(DISCOURSE_SERVER_URL, api_key='aaaa')
        response = client.topics_page()

        self.assertEqual(response, body)

        # Check request params
        expected = {
                    'api_key' : ['aaaa']
                   }

        req = httpretty.last_request()

        self.assertEqual(req.method, 'GET')
        self.assertRegex(req.path, '/latest.json')
        self.assertDictEqual(req.querystring, expected)

        # Call API selecting a page
        response = client.topics_page(page=1)

        self.assertEqual(response, body)

        # Check request params
        expected = {
                    'api_key' : ['aaaa'],
                    'page' : ['1']
                   }

        req = httpretty.last_request()

        self.assertDictEqual(req.querystring, expected)

    @httpretty.activate
    def test_topic(self):
        """Test topic API call"""

        # Set up a mock HTTP server
        body = read_file('data/discourse_topic_1148.json')
        httpretty.register_uri(httpretty.GET,
                               DISCOURSE_TOPIC_URL_1148,
                               body=body, status=200)

        # Call API
        client = DiscourseClient(DISCOURSE_SERVER_URL, api_key='aaaa')
        response = client.topic(1148)

        self.assertEqual(response, body)

        # Check request params
        expected = {
                    'api_key' : ['aaaa'],
                   }

        req = httpretty.last_request()

        self.assertEqual(req.method, 'GET')
        self.assertRegex(req.path, '/t/1148.json')
        self.assertDictEqual(req.querystring, expected)

    @httpretty.activate
    def test_post(self):
        """Test post API call"""

        # Set up a mock HTTP server
        body = read_file('data/discourse_post.json')
        httpretty.register_uri(httpretty.GET,
                               DISCOURSE_POST_URL_1,
                               body=body, status=200)

        # Call API
        client = DiscourseClient(DISCOURSE_SERVER_URL, api_key='aaaa')
        response = client.post(21)

        self.assertEqual(response, body)

        # Check request params
        expected = {
                    'api_key' : ['aaaa'],
                   }

        req = httpretty.last_request()

        self.assertEqual(req.method, 'GET')
        self.assertRegex(req.path, '/posts/21.json')
        self.assertDictEqual(req.querystring, expected)


if __name__ == "__main__":
    unittest.main(warnings='ignore')
