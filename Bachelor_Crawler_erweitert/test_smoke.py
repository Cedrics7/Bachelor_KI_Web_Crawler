from Bachelor_Crawler_vollstaendig.domain_model import DomainModel


def test_domain_model_scores_keywords():
    score, kws = DomainModel().score_text("Der Bebauungsplan und die Sanierung der Straße wurden beschlossen")
    assert score > 0
    assert kws
