# -*- coding: utf-8 -*-
# vim:ts=4:sw=4:expandtab

from muacrypt.recommendation import Recommendation


class TestRecommendation:

    def test_empty_peer_state(self, account_maker):
        sender, recipient = account_maker(), account_maker()
        peerstate = sender.get_peerstate(recipient.addr)
        rec = Recommendation({recipient.addr: peerstate})
        assert rec.target_keys()[recipient.addr] is None
        assert rec.ui_recommendation() == 'disable'
