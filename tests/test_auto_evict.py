# SPDX-License-Identifier: BUSL-1.1
# Copyright © 2026 Zyvor AI Labs Private Limited
import unittest
from server.app import auto_evict_once, auto_evict_settings, start_auto_evict, ControlPlaneServer
from tests.test_idle import IdleEvictionTests as Base, HOUR

class AutoEvictTests(Base):
    """Reuses the idle-eviction fixture: real deploy path, real gateway traffic, fake clock."""
    def test_idle_model_is_evicted_and_busy_one_survives(self):
        self.store.model('idle', dict(memoryGiB=4)); self.store.model('busy', dict(memoryGiB=4))
        idle_job = self.deploy('idle')
        busy_job = self.deploy('busy')
        self.advance(2 * HOUR - 60)
        self.chat('busy')
        self.advance(120)
        self.assertEqual(auto_evict_once(self.store, HOUR), [idle_job])
        self.assertIn(self.state(idle_job), ('cancelling', 'cancelled'))
        self.assertEqual(self.state(busy_job), 'running')

    def test_fresh_deploy_is_not_evicted(self):
        self.store.model('m', dict(memoryGiB=4))
        self.now += 2 * 86400
        self.store.register('mini', dict(budgetGiB=16, slots=4, runtimes=['serve']))
        self.deploy('m')
        self.assertEqual(auto_evict_once(self.store, HOUR), [])

    def test_settings_default_off_and_validation(self):
        self.assertEqual(auto_evict_settings({}), (0, 60))
        self.assertEqual(auto_evict_settings({'autoEvictIdleSeconds': 600, 'autoEvictIntervalSeconds': 5}), (600, 5))
        self.assertEqual(auto_evict_settings({}, 900), (900, 60))
        for bad in ({'autoEvictIdleSeconds': 30}, {'autoEvictIdleSeconds': -1}, {'autoEvictIdleSeconds': 'x'},
                    {'autoEvictIdleSeconds': float('nan')}, {'autoEvictIdleSeconds': 31 * 86400},
                    {'autoEvictIntervalSeconds': 0}):
            with self.assertRaises(ValueError, msg=bad): auto_evict_settings(bad)

    def test_loop_is_off_when_disabled_and_stops_with_server(self):
        self.assertIsNone(start_auto_evict(type('S', (), {})(), 0, 1))
        server = ControlPlaneServer(('127.0.0.1', 0), type('H', (), {}))
        server.store = self.store
        thread = start_auto_evict(server, HOUR, 0.05)
        self.assertTrue(thread.is_alive())
        server.server_close()
        thread.join(2)
        self.assertFalse(thread.is_alive())

if __name__ == '__main__': unittest.main()
