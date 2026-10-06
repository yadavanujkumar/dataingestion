# 06_Worked_Example_Engagement_Report.docx

HOWL PLATFORM · DOCUMENT 06

Worked Example: Engagement Report

The existing engagement-rate sheet analysed and rebuilt on the platform.

Version 0.1 (draft)  ·  28 September 2026  ·  Prepared for the HOWL tech team  ·  First brand: Ampere

The existing engagement-rate sheet, what its numbers show, the problems found in it, and how the same report is rebuilt properly on the platform.

1. What the sheet contains

Three tables of engagement rate: paid, organic and total.

Four platforms (Instagram, Facebook, YouTube, LinkedIn) across 13 months, August 2025 to August 2026.

A summary table with &quot;AVG Organic&quot;, &quot;AVG Paid&quot; and &quot;AVG Total&quot; per platform.

On the platform this is one deliverable, engagement_rate_report, fed by two domains: paid and organic.

2. Problems found

2.1 &quot;AVG Total&quot; is not an average

Its values (93.13%, 24.98%, 18.20%, 20.54%) are exactly the October 2025 column of the total table. The formula points at one cell.

2.2 The other averages skip a month and weight months equally

&quot;AVG Paid&quot; and &quot;AVG Organic&quot; are simple averages of August 2025 to July 2026 and leave out August 2026. Example: Instagram organic sums to 58.52 over those 12 months; 58.52 ÷ 12 = 4.88%.

LinkedIn paid&apos;s 10.40% averages only the three months with data: (12.20 + 12.10 + 6.90) ÷ 3.

Averaging monthly percentages gives a 500-impression month the same weight as a 5-million-impression month. The correct method is total engagements divided by total impressions for the period.

2.3 &quot;Total&quot; cannot be paid plus organic

Instagram, August 2025: paid 16.45%, organic 0.20%, total 22.93%. A combined rate has to fall between its two parts.

Instagram, December 2025: total 133.98%, which is over 100%.

So &quot;total&quot; uses a different denominator, possibly organic reach or followers. The definition needs to be confirmed.

2.4 LinkedIn totals do not match organic

With no paid LinkedIn activity, total should equal organic. It does for September, December and January, but not for August 2025 (organic 3.57%, total 13.95%) or March 2026 (4.70% versus 5.18%), suggesting data pulled at different times or from different sources.

2.5 &quot;Engagement&quot; means different things per platform

YouTube paid at 50% to 60% is almost certainly view rate (views ÷ impressions), not engagement. Without one definition per platform the rows cannot be compared.

2.6 Outliers

August 2026 organic shows Instagram 37.38% and LinkedIn 60.00%. These are likely small denominators or boosted posts counted as organic, and exactly what the review queue should stop.

3. What to ingest instead

Ingest counts, never rates. Rates are calculated by the generator.

Row

Source (via Windsor unless noted)

Engagements

Divided by

Instagram / Facebook paid

Meta Ads

post engagements

impressions

Instagram / Facebook organic

IG / FB insights, or Meta Business Suite CSV

likes + comments + shares + saves

impressions (or reach)

YouTube paid

Google Ads (video campaigns)

engagements; views kept as a separate column

impressions

YouTube organic

YouTube Analytics

likes + comments + shares

views

LinkedIn paid

LinkedIn Ads

total engagements

impressions

LinkedIn organic

LinkedIn page analytics

clicks + reactions + comments + shares

impressions

4. How it flows through the platform

Ingest. The Windsor puller fetches daily data for each paid and organic source; CSVs cover any gaps.

Normalize. Adapters write long-format rows, one per date, platform and paid/organic type, into canonical_paid (v2) and canonical_organic.

Classify. Posts and campaigns are tagged paid or organic. Boosted posts are the ambiguous case and go to review the first time; the decision is remembered.

Generate. engagement_rate_report computes, per month and platform: paid rate, organic rate and total rate, each as a ratio of sums; period averages the same way. &quot;-&quot; stays empty (no campaign ran), never 0%.

Check. Any rate above 100%, or above three times the platform&apos;s median, becomes a review item before the file is built.

Deliver. An xlsx in the same three-table layout the team already uses, plus a notes tab explaining definitions.

Example normalized rows

date        platform   type     impressions  reach   engagements  video_views  source_id

2025-08-01  instagram  paid     184,220      91,400  30,304       -            ampere-meta-ads

2025-08-01  instagram  organic  12,850       9,710   26           -            ampere-ig-insights

Figures above are illustrative, not real Ampere data.

5. Loading the history in the sheet

Re-pulling August 2025 to August 2026 from the APIs is better, because it gives counts. Check how far back each platform keeps data; organic insights usually keep the least. For months that cannot be re-pulled:

The legacy importer reads the three tables and writes one row per cell: month, platform, type, metric = engagement_rate, value.

&quot;-&quot; becomes empty; &quot;16.45%&quot; becomes 0.1645.

Rows are marked source = legacy because they cannot be recalculated or combined correctly.

The problem cells in section 2 go straight to the review queue.

6. Questions for whoever built the sheet

What is the exact formula for Total, in particular its denominator?

What counts as &quot;engagement&quot; on each platform, and does YouTube include views?

Is reporting monthly, and should averages cover the last 12 complete months or include the current month?

Are boosted posts counted as paid or organic?