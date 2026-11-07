# {{ hub.title }}

{% if intro %}{{ intro }}

{% endif %}Canonical page: {{ canonical }}
Source: Afefehub (https://afefehub.com). Ranking method: https://afefehub.com/about/methodology
{% if hub.top %}
## Ranked by reviewers
{% for li in hub.top %}{% set b = li.business %}
{{ loop.index }}. [{{ b.name | oneline }}]({{ site }}{{ li.path }}.md) — {{ category(b.category) }}{% if b.city %}, {{ b.city }}{% endif %}; {{ plural(b.review_count, 'review') }}, {{ pct(b) }}% recommend{% if b.average_rating is not none %}, {{ '%.1f' % b.average_rating }}/5{% endif %}.{% if li.summary and li.summary.headline %} {{ li.summary.headline | oneline }}{% endif %}{% endfor %}
{% endif %}{% if hub.children %}
## {{ browse_title }}
{% for c in hub.children %}
- [{{ c.label }}]({{ site }}{{ c.path }}.md) ({{ c.count }}){% endfor %}
{% endif %}
