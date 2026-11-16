import unittest
from continue_crawl import active,checkpoint_published,resumable,resume_at

class ContinuationTests(unittest.TestCase):
    def test_requires_saved_pending_work(self):
        self.assertTrue(resumable({'coverage':{'queued_urls':3},'crawl_status':{'last_error':''}}))
        self.assertFalse(resumable({'coverage':{'queued_urls':0}}))
        self.assertFalse(resumable({}))
    def test_server_cooldown_can_resume_but_unexpected_errors_stop(self):
        base={'coverage':{'queued_urls':3}}
        self.assertTrue(resumable({**base,'crawl_status':{'last_error':'Five consecutive server/network errors; crawl paused until tomorrow'}}))
        self.assertFalse(resumable({**base,'crawl_status':{'last_error':'robots.txt disallows forum index'}}))
        self.assertFalse(resumable({**base,'crawl_status':{'last_error':'Parser crashed'}}))
    def test_waits_for_server_cooldown(self):
        self.assertEqual(resume_at({'crawl_status':{'pause_until':'2000'}},1000),2000)
        self.assertEqual(resume_at({'crawl_status':{'pause_until':'100'}},1000),1060)
        with self.assertRaises(ValueError):resume_at({'crawl_status':{'pause_until':'Infinity'}},1000)
    def test_requires_checkpoint_and_index_from_the_same_job(self):
        checkpoint={'name':'Save resumable checkpoint','conclusion':'success'}
        index={'name':'Publish immutable index for Sites','conclusion':'success'}
        self.assertTrue(checkpoint_published([{'steps':[checkpoint,index]}]))
        self.assertFalse(checkpoint_published([{'steps':[checkpoint]}]))
        self.assertFalse(checkpoint_published([{'steps':[checkpoint,{**index,'conclusion':'failure'}]}]))
    def test_does_not_duplicate_active_or_queued_jobs(self):
        for status in ['queued','pending','in_progress','waiting']:
            self.assertTrue(active([{'status':status}]))
        self.assertFalse(active([{'status':'completed'}]))

if __name__=='__main__':unittest.main()
