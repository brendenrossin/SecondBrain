# Implementation Prompt: Task Ordering on Frontend

## Context
The tasks page currently shows tasks in "first appearance" order (the order they were first encountered in daily notes). This produces a seemingly random order where a task due in 13 days appears before one due in 12 days. The user wants tasks sorted by due date within each sub-project, and sub-projects sorted by their most urgent task.

## What to Change

### 1. Sort tasks within each sub-project by due date (soonest first)

**File:** `frontend/src/components/tasks/TaskCategory.tsx`

After grouping tasks by sub_project in the `grouped` Map, sort the tasks within each group before rendering:

```
Sort order for tasks:
1. Overdue (most overdue first)
2. Due today
3. Due tomorrow
4. Due later (soonest first)
5. No due date (last)
```

The `TaskResponse` type (check `frontend/src/lib/api.ts` or `frontend/src/types/`) should have `due_date: string | null` and `days_until_due: number | null` fields. Use `due_date` for sorting (it's a `YYYY-MM-DD` string, so string comparison works for chronological order). Tasks with `null` due_date sort to the bottom.

### 2. Sort sub-projects within each category by most urgent task

**File:** `frontend/src/components/tasks/TaskCategory.tsx`

After grouping into the `grouped` Map, sort the sub-project entries before rendering:

```
Sort order for sub-projects:
1. Compute "urgency" = the earliest (minimum) due_date among all tasks in the sub-project
2. Sub-projects with earlier urgency dates come first
3. If two sub-projects have the same urgency date, the one with more tasks comes first
4. Sub-projects where ALL tasks have null due_date come last
5. Empty sub_project key ("") tasks (no sub-project) sort based on their urgency like any other group
```

### Implementation Details

**Read these files first:**
- `frontend/src/components/tasks/TaskCategory.tsx` — where grouping happens
- `frontend/src/components/tasks/TaskSubProject.tsx` — where tasks are rendered (may need sorting here instead)
- `frontend/src/components/tasks/TaskTree.tsx` — parent orchestrator
- `frontend/src/lib/api.ts` — TaskResponse type definition

**Sorting approach:**
- Do all sorting on the frontend (not backend) — keeps the API simple and lets us change sort logic without server restarts
- Sort inside `TaskCategory.tsx` since it has access to both the sub-project grouping and the task lists
- Use `useMemo` for sort computations to avoid re-sorting on every render

**The sort for tasks is simply:**
```typescript
tasks.sort((a, b) => {
  if (!a.due_date && !b.due_date) return 0;
  if (!a.due_date) return 1;   // null dates last
  if (!b.due_date) return -1;
  return a.due_date.localeCompare(b.due_date);  // YYYY-MM-DD string comparison
});
```

**The sort for sub-projects uses each group's minimum due_date:**
```typescript
// For each sub-project group, find the earliest due_date
const urgency = (tasks: TaskResponse[]) => {
  const dates = tasks.map(t => t.due_date).filter(Boolean) as string[];
  return dates.length > 0 ? dates.sort()[0] : null;
};

entries.sort(([keyA, tasksA], [keyB, tasksB]) => {
  const urgA = urgency(tasksA);
  const urgB = urgency(tasksB);
  if (!urgA && !urgB) return tasksB.length - tasksA.length; // more tasks first
  if (!urgA) return 1;
  if (!urgB) return -1;
  const cmp = urgA.localeCompare(urgB);
  if (cmp !== 0) return cmp;
  return tasksB.length - tasksA.length; // tie-break: more tasks first
});
```

## Testing

**No automated tests needed** — this is a pure display-order change with no business logic impact.

**Manual QA:**
1. Open the tasks page
2. Verify Personal tasks: overdue tasks appear first, then tasks due soonest
3. Verify sub-projects within Personal: the sub-project with the most urgent task appears first
4. Verify AT&T sub-projects: AI Receptionist vs Welcome Agent should be ordered by their most urgent task
5. Verify tasks with no due date appear at the bottom of their group

## Out of Scope
- Backend sorting (keep API returning in natural order)
- Sorting categories (already alphabetical, which is fine)
- Adding sort controls or toggles to the UI
- Changing the task aggregator's sort logic (it already sorts for the Markdown file)

## After Implementation
- Rebuild frontend: `cd /Users/brentrossin/SecondBrain/frontend && npm run build`
- Restart frontend service:
  ```
  launchctl unload ~/Library/LaunchAgents/com.secondbrain.ui.plist
  sleep 2 && kill -9 $(lsof -ti:7860) 2>/dev/null
  launchctl load ~/Library/LaunchAgents/com.secondbrain.ui.plist
  sleep 5 && curl -s -o /dev/null -w "%{http_code}" http://localhost:7860/
  ```
- Verify with browser

## Commit Workflow
Write code → `code-simplifier` → commit with message like "Sort tasks by due date and sub-projects by urgency on tasks page"
