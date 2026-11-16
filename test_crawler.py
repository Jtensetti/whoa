"""Recovery tests use isolated temporary databases, never the forum archive."""
import contextlib
import pathlib
import sqlite3
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import requests
import main


def response(code=200, **headers):
    result=requests.Response()
    result.status_code=code
    result.headers={'content-type':'text/html; charset=utf-8',**headers}
    result.encoding='utf-8'
    result._content=b'<html></html>'
    return result


class CrawlRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.stack=contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        directory=self.stack.enter_context(tempfile.TemporaryDirectory())
        self.directory=pathlib.Path(directory)
        for name,value in [('DB',str(self.directory/'test.db')),('BATCH',10),('SECONDS',300),('DELAY',3)]:
            self.stack.enter_context(patch.object(main,name,value))
        self.clock=self.stack.enter_context(patch.object(main.time,'time',return_value=1000))
        self.stack.enter_context(patch.object(main.time,'sleep'))
        self.session=Mock()
        self.stack.enter_context(patch.object(main.requests,'Session',return_value=self.session))
        robots=types.SimpleNamespace(can_fetch=lambda *args:True,crawl_delay=lambda *args:None)
        self.stack.enter_context(patch.object(main,'can_crawl',return_value=robots))
        self.stack.enter_context(patch.object(main,'parse_page',return_value=('Test title','Test category','Hej',set())))
        self.bad=main.ROOT+'/forum/test/category/100/1.aspx'
        self.good=main.ROOT+'/forum/test/category/101/1.aspx'
        with contextlib.closing(main.db()) as c:
            c.execute("insert into visited values (?,200,'test')",(main.ROOT+main.ROOT_PATH,))
            c.execute("insert into crawl_status values ('frontier_schema','2')")
            main.enqueue(c,self.bad);main.enqueue(c,self.good);c.commit()

    def query(self,sql,params=()):
        with contextlib.closing(sqlite3.connect(main.DB)) as c:
            return c.execute(sql,params).fetchall()

    def test_http_500_is_deferred_and_other_page_is_indexed(self):
        self.session.get.side_effect=[response(500),response()]
        main.crawl_batch()
        self.assertEqual(self.query('select url from pages'),[(self.good,)])
        self.assertEqual(self.query('select url,attempts,next_attempt from pending'),[(self.bad,1,1060.0)])
        self.assertEqual(self.query('select url,reason from failures'),[(self.bad,'HTTP 500')])
        self.assertEqual(self.query("select value from crawl_status where key='last_error'"),[('',)])

    def test_successful_retry_clears_failure_and_preserves_short_posts(self):
        self.session.get.side_effect=[response(500),response()]
        main.crawl_batch()
        self.clock.return_value=2000
        self.session.get.side_effect=[response()]
        main.crawl_batch()
        self.assertEqual(self.query('select count(*) from pages'),[(2,)])
        self.assertEqual(self.query('select body from pages where url=?',(self.bad,)),[('Hej',)])
        self.assertEqual(self.query('select * from failures'),[])
        self.assertEqual(self.query('select * from pending'),[])

    def test_timeout_does_not_block_other_pages(self):
        self.session.get.side_effect=[requests.Timeout('Timed out'),response()]
        main.crawl_batch()
        self.assertEqual(self.query('select url from pages'),[(self.good,)])
        self.assertEqual(self.query('select attempts from pending'),[(1,)])

    def test_retry_deadline_survives_reopening_database(self):
        with contextlib.closing(main.db()) as c:
            main.defer_url(c,self.bad,'HTTP 500')
        with contextlib.closing(main.db()) as c:
            self.assertEqual(main.next_pending(c,1),self.good)
            main.defer_url(c,self.good,'HTTP 500')
            self.assertIsNone(main.next_pending(c,1))
            self.assertEqual(main.next_pending(c,1,now=1061),self.bad)

    def test_repeated_failure_increases_backoff(self):
        with contextlib.closing(main.db()) as c:
            self.assertEqual(main.defer_url(c,self.bad,'HTTP 500'),1060)
            self.assertEqual(main.defer_url(c,self.bad,'HTTP 500'),1120)
            self.assertEqual(main.defer_url(c,self.bad,'HTTP 500',minimum_wait=600),1600)

    def test_rate_limit_stops_host_and_next_run_honors_cooldown(self):
        self.session.get.side_effect=[response(429,**{'Retry-After':'1200'}),response()]
        with self.assertRaisesRegex(RuntimeError,'Server rate limit'):
            main.crawl_batch()
        self.assertEqual(self.session.get.call_count,1)
        self.assertEqual(self.query("select value from crawl_status where key='pause_until'"),[('2200.0',)])
        self.session.get.reset_mock()
        with self.assertRaisesRegex(RuntimeError,'cooldown'):
            main.crawl_batch()
        self.session.get.assert_not_called()
        self.assertEqual(self.query('select count(*) from pending'),[(2,)])

    def test_retry_after_on_unavailable_server_pauses_host(self):
        self.session.get.side_effect=[response(503,**{'Retry-After':'120'}),response()]
        with self.assertRaisesRegex(RuntimeError,'Retry-After'):
            main.crawl_batch()
        self.assertEqual(self.session.get.call_count,1)
        self.assertEqual(self.query('select count(*) from visited'),[(1,)])

    def test_consecutive_server_errors_pause_without_losing_queue(self):
        with contextlib.closing(main.db()) as c:
            for number in range(102,106):main.enqueue(c,main.ROOT+f'/forum/test/category/{number}/1.aspx')
            c.commit()
        self.session.get.side_effect=[response(500) for _ in range(6)]
        with self.assertRaisesRegex(RuntimeError,'Five consecutive'):
            main.crawl_batch()
        self.assertEqual(self.session.get.call_count,5)
        self.assertEqual(self.query('select count(*) from pending'),[(6,)])

    def test_existing_checkpoint_schema_is_upgraded_without_losing_urls(self):
        legacy=str(self.directory/'legacy.db')
        with sqlite3.connect(legacy) as c:
            c.execute('create table pending(url text primary key,priority integer not null default 0)')
            c.execute('insert into pending values (?,20)',(self.bad,))
        with patch.object(main,'DB',legacy),contextlib.closing(main.db()) as c:
            self.assertEqual(c.execute('select url,priority,next_attempt,attempts from pending').fetchall(),[(self.bad,20,0,0)])

    def test_retry_after_http_date_and_invalid_values(self):
        self.assertEqual(main.retry_after_seconds('Thu, 01 Jan 1970 00:20:00 GMT',now=1000),200)
        self.assertEqual(main.retry_after_seconds('invalid'),0)
        self.assertEqual(main.retry_after_seconds('-1'),0)


if __name__=='__main__':unittest.main()
