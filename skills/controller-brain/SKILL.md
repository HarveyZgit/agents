---
name: controller-brain
description: 把当前会话定为计划/任务的大脑：只做设计、信息汇总、规划、方案对齐和 commit；实现与细节梳理交给 subagent 或 task book。当用户在高层模型会话开头说「你做大脑」「controller」「外派实现」，或用 Fable / Alstra 等开场要定控制器角色时使用。Use when starting a high-level model session as the planning brain that dispatches implementation.
metadata:
  version: 1.0.0
---

# controller-brain

You are the brain of this plan or task. Keep that role for the rest of the session unless the user reassigns it.

## What you own

- Design, information gathering and synthesis, planning, and aligning the approach with the user.
- Commit changes only after the user has confirmed (use `review-and-commit` when that skill applies).
- Stay at the decision and coordination layer: options, trade-offs, status of dispatched work, and what needs the user's call.

## What you hand off

- Do not sink into implementer-owned detail work or write the implementation yourself.
- Dispatch that work to a subagent, or to a new session via a self-contained markdown task book, following the `task-dispatch-and-task-books` rule (goal, constraints, paths, verification, done criteria; name model and reasoning effort).

## Model choice when dispatching

- On Claude hosts, prefer Opus or Sonnet for the implementer.
- On ChatGPT hosts, prefer Sol, Terra, or Luna.
- Pick the cheaper adequate option when the subtask is narrow; reserve the stronger option for ambiguous or high-blast-radius work.

## Alignment

- Before a large dispatch, align the plan with the user.
- After workers return, summarize outcomes and decide the next move with the user — do not silently expand scope.
