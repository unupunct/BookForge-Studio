"""Tiny offline language guess for imported manuscripts (stop-word frequency)."""
from __future__ import annotations

import re

STOP: dict[str, set[str]] = {
    "en": set("the of and to in is that it was for on are as with his they at be this from have or by one had not but what all were when we there can an your which their said if do will each about how up out them then she many some so these would other into has more her two like him see time could no make than first been its who now people my made over did down only way find use may water long little very after words called just where most know".split()),
    "ro": set("și si de la în in un o cu pe nu că ca ce din se sunt este care mai pentru dar sau mi mă ma te ne le lui ei el ea noi voi ei acest această acea fi am ai are au fost va vor dacă cum când unde cine cât așa asa doar prin peste sub între despre fără fara încă inca nici tot toate toți cel cea cei cele mea mele tău tale său sale ne-am n-am nu-mi".split()),
    "fr": set("le la les de des du un une et est en que qui dans pour pas sur au avec ce il elle je nous vous ils elles se ne plus par mais ou où son sa ses leur être avoir fait comme tout cette ces aux très".split()),
    "de": set("der die das und ist in den von zu mit sich des auf für nicht ein eine als auch es an werden aus er hat dass sie nach wird bei einer um am sind noch wie einem über einen so zum war haben nur oder aber vor zur bis mehr durch man sein wurde sei".split()),
    "es": set("el la los las de del y en que es un una por con para no se su al lo como más pero sus le ya o este sí porque esta entre cuando muy sin sobre también me hasta hay donde quien desde todo nos durante todos uno les ni contra otros ese eso ante ellos e esto mí antes algunos qué unos yo otro otras otra él tanto esa estos mucho quienes nada muchos cual poco ella estar estas algunas algo nosotros".split()),
    "it": set("il lo la i gli le di a da in con su per tra fra un uno una e è che non si più come ma anche se ha sono del della dei delle al alla nel nella questo questa quello loro suo sua mi ti ci vi ne io tu lui lei noi voi essere avere fatto molto tutto".split()),
    "pt": set("o a os as de do da dos das e em um uma que não se para com por mais como mas foi ao ele ela seu sua ou ser quando muito há nos já está eu também só pelo pela até isso entre era depois sem mesmo aos ter seus quem nas me esse eles estão você tinha foram essa num nem suas meu às minha têm numa".split()),
    "hu": set("a az és hogy nem is egy de ez azt van volt meg már még csak mint vagy el be ki fel le át rá ők mi te én ő ti ön itt ott aki ami amit ha ezt azért mert után előtt között nagyon minden lesz lett kell".split()),
    "pl": set("i w nie na się z do to że jest jak ale po co tak za od przez dla o czy są był była było tylko go ja ty on ona my wy oni one tego jego jej ich mnie ci tam tu już jeszcze bardzo może gdy kiedy który która które".split()),
    "nl": set("de het een en van ik te dat die in is niet op zijn met voor er maar om ook als dan nog aan bij of uit je ze had dit hem zo wat wel haar werd naar kan mijn hij ons heeft zij hun over".split()),
}
RO_CHARS = set("ăâîșțşţĂÂÎȘȚŞŢ")
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def detect_language(text: str, min_words: int = 40) -> str | None:
    words = [w.lower() for w in _WORD.findall(text[:60000])]
    if len(words) < min_words:
        return None
    scores: dict[str, float] = {}
    for lang, stops in STOP.items():
        scores[lang] = sum(1 for w in words if w in stops) / len(words)
    ro_chars = sum(1 for ch in text[:60000] if ch in RO_CHARS)
    if ro_chars and ro_chars / len(words) > 0.01:
        scores["ro"] += 0.04  # Romanian-only letters are a strong signal
    best = max(scores, key=scores.get)
    ordered = sorted(scores.values(), reverse=True)
    if scores[best] < 0.06 or ordered[0] - ordered[1] < 0.015:
        return None
    return best
