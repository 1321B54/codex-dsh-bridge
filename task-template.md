# Authorized execution task

## Goal
Describe one bounded task, not the whole project.

## Inputs
List files already staged in this isolated workspace. Do not copy credentials.

## Allowed edits
List the exact files or module boundaries that may be changed.

## Forbidden actions
No changes outside the task workspace; no credentials, system configuration,
global installation, network deployment, Git commits/pushes, or subagents.

## Acceptance
State the commands to run and expected behavior, including regression checks.

## Deliverable
Return changed file names, test commands/results, and unresolved issues.
The coordinator will independently inspect changes and make the acceptance decision.
