# 00_Start_Here.docx

HOWL PLATFORM · DOCUMENT 00

Start Here

Folder guide and reading order for the HOWL Platform documentation.

Version 0.1 (draft)  ·  28 September 2026  ·  Prepared for the HOWL tech team  ·  First brand: Ampere

This folder holds the design documentation for the HOWL Platform: what it is, why it exists, how it works, which tools it uses and why, and how to build it in phases. Start here to decide which document to read first.

What is in this folder

File

What it covers

Read it when

00_Start_Here.docx

This guide. Folder map, reading order, glossary pointer.

First

01_Platform_Overview.docx

The basics: what the platform is, the problem it solves, who uses it, core concepts, design principles, what it is not.

Before anything else

02_Workflow_and_Architecture.docx

The full architecture, every component, the end-to-end run workflow, the classification loop, the review process, the media-plan branch, error handling and security.

Before designing or coding any component

03_Tool_Stack_and_Rationale.docx

Every tool choice, why it was picked, and the alternatives that were considered and rejected.

When choosing or questioning a tool

04_Data_Model_and_Contracts.docx

The brand manifest, canonical schemas, database tables, decision ledger, generator contract and metric dictionary.

Before writing migrations, adapters or generators

05_Phase_Wise_Build_Plan.docx

The build broken into Phase 0 to Phase 5 plus scheduling, each with tasks, outputs, an exit test and risks. Also the repo layout.

When planning sprints

06_Worked_Example_Engagement_Report.docx

The existing engagement-rate sheet analysed, and how it is rebuilt properly on the platform.

As a concrete reference for how a report moves through the system

07_Decisions_Risks_Open_Questions.docx

The decision log, the risk register and the questions still to answer.

Before Phase 0 kicks off, and at each phase review

diagrams/

Full-resolution PNGs of every diagram used in these documents.

For slides or printing

Suggested reading order

Role

Read

Skim

Founder or account lead

01, 05, 07

02 (diagrams only), 06

Developer building the platform

01, 02, 04, 05

03, 06, 07

Analyst working the review queue

01, 02 (sections on classification and review), 06

04

New team member

00, 01, then the system map in 02

Everything else as needed

The platform in three sentences

A brand is onboarded once: its data sources, brand identity and classification rules are written into a single brand manifest. From then on, every report for that brand is generated on demand by code that reads one clean, shared store of that brand&apos;s data. People only step in to resolve items the system is unsure about and to check a draft before it goes to the client.

Diagrams

diagrams/system_map.png: the whole system on one page (sources, ingestion, core, deliverables, delivery, media-plan branch).

diagrams/layers.png: the two-layer architecture and the boundary between the platform and the reports.

diagrams/learning_loop.png: how classification uses the decision ledger so review work shrinks over time.

diagrams/media_plan.png: how a media plan generates the names that later join actuals back to the plan.

Interactive versions (private until shared from the page&apos;s Share menu): the HOWL System Map at claude.ai/artifact/9ERSJiX8Kn7qJGZY1GEFJj and the HOWL Platform Blueprint at claude.ai/artifact/YRBq2i93cZBLqZAwfNeEAy.

Source of these documents

These documents expand the HOWL Platform Developer Build Specification (HOWL_Platform_Developer_Build_Spec.md.docx). Where they differ from the spec, the difference is intentional and is recorded as a decision in document 07.