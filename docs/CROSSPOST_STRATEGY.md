# Postal AutoClip cross-posting strategy

## Default rule

For original Postal/JustGoinPostal short-form content, use **one strong core clip across YouTube Shorts, TikTok, and Instagram Reels on the same local calendar date**.

Postal AutoClip should not deliberately turn Monday's YouTube clip into Wednesday's TikTok clip just because one platform has historically liked that event type more.

Platform analytics are used to optimize the post, not hide the story from another audience.

## What stays the same

- Core gameplay moment / story
- Payoff
- Brand identity
- Main captions and hook concept
- Calendar date

## What may change by platform

- Post title / caption / hashtags
- Cover treatment
- CTA
- Exact posting time on that same date
- Render length (22s / 38s / 58s) only after enough platform-specific evidence exists

## Platform learning

Every approved clip still has a global quality score. YouTube, TikTok, and Instagram also learn separate audience profiles from mature post analytics.

Example:

| Clip | Global | YouTube fit | TikTok fit | Instagram fit |
| --- | ---: | ---: | ---: | ---: |
| PvP smite | 92 | 79 | 98 | 91 |
| Raid purple | 95 | 97 | 88 | 94 |

Both clips can still be published everywhere. Platform fit can influence packaging and, once enough history exists, which rendered duration is used.

## Timing

A synchronized release does not have to mean the exact same minute. If each platform's own audience analytics later show different active windows, Postal AutoClip may schedule different times **on the same date**.

Small minute-level staggering is also useful operationally and can reduce repeated exposure for followers who overlap heavily across platforms.

For time-sensitive announcements or news, prefer effectively simultaneous publishing everywhere.

## Evidence behind this rule

- Buffer's 2026 cross-posting guide defines cross-posting as publishing the same or lightly adapted content across multiple networks, including at the same time, and recommends platform-specific captions/hashtags/timing rather than creating fresh content for every network: https://buffer.com/resources/how-to-crosspost/
- Sprout Social's September 2026 cross-posting guide says cross-posting can be simultaneous or network-specific, recommends clean watermark-free short-form video across Reels/TikTok/Shorts, and uses a same-day example with different send times based on each network's audience: https://sproutsocial.com/insights/cross-posting-on-social-media/
- YouTube's Shorts guidance emphasizes sustainable consistency and audience response rather than a required cadence or cross-platform delay: https://support.google.com/youtube/answer/13616979 and https://support.google.com/youtube/answer/11914225

## Product invariant

When `synchronized_crosspost_enabled` is true, the weekly planner must preserve the same clip order and local calendar date across selected platforms. Platform-specific models must not reshuffle different clips onto different days.
