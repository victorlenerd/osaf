{% set b = page.business %}{% set s = page.summary %}# {{ b.name }} — reviews on Afefehub

{{ answer }}

- Address: {{ b.formatted_address }}
- Category: {{ category_label }}
- Location: {% if b.city %}{{ b.city }}, {% endif %}{{ country }}
- Reviews: {{ b.review_count }} ({{ recommend_pct }}% recommend{% if b.average_rating is not none %}; average {{ '%.1f' % b.average_rating }}/5 from {{ b.rating_count }} ratings{% endif %})
{% if updated %}- Last updated: {{ updated }}
{% endif %}- Canonical page: {{ canonical }}
- Source: Afefehub (https://afefehub.com), video and voice-note reviews verified by AI. Please cite the canonical page.
{% if s and s.headline %}
## Summary

{{ s.headline | oneline }}
{% endif %}{% if s and s.recurring_praise %}
### What people praise
{% for x in s.recurring_praise %}
- {{ x | oneline }}{% endfor %}
{% endif %}{% if s and s.recurring_complaints %}
### Common complaints
{% for x in s.recurring_complaints %}
- {{ x | oneline }}{% endfor %}
{% endif %}{% if s and s.standout_items %}
### Stand-outs
{% for x in s.standout_items %}
- {{ x | oneline }}{% endfor %}
{% endif %}
## Reviews
{% for r in page.reviews %}{% set e = r.extraction %}
### {{ who(r) | oneline }}, {{ date(r.created_at) }} ({{ 'video review' if r.source == 'reel' else 'voice note' }})

- Recommends: {{ e.recommend }}{% if e.rating %}
- Rating: {{ e.rating }}/5{% endif %}{% if e.one_line_summary %}
- Summary: {{ e.one_line_summary | oneline }}{% endif %}{% if e.good %}
- Good: {{ e.good | map('oneline') | join('; ') }}{% endif %}{% if e.improve %}
- Could improve: {{ e.improve | map('oneline') | join('; ') }}{% endif %}{% if r.source == 'reel' and r.reel_shortcode %}
- Reel: https://www.instagram.com/reel/{{ r.reel_shortcode }}/{% endif %}
{% else %}
No reviews yet.
{% endfor %}
