import { deleteMemoryTaskById } from '../api';

export type VerifiedTaskDeleteTarget = {
  id: string;
  title: string;
};

export type VerifiedTaskDeleteResult =
  | {
      ok: true;
      deletedTaskId: string;
      message: string;
    }
  | {
      ok: false;
      message: string;
    };

export async function deleteVerifiedGlobalTask(
  target: VerifiedTaskDeleteTarget,
): Promise<VerifiedTaskDeleteResult> {
  const taskId = target.id.trim();
  const title = target.title.trim();
  if (!taskId || !title) {
    return {
      ok: false,
      message: 'QMeet could not verify one task identity to delete. No task was changed.',
    };
  }

  try {
    const response = await deleteMemoryTaskById(taskId);
    if (!response.ok || response.deletedTaskId !== taskId) {
      return {
        ok: false,
        message:
          'The backend did not verify deletion of the confirmed task identity. No different task was deleted.',
      };
    }

    return {
      ok: true,
      deletedTaskId: taskId,
      message: response.message || `Deleted task: ${title}`,
    };
  } catch (error) {
    const detail =
      error instanceof Error && error.message.trim()
        ? error.message.trim()
        : 'The canonical task delete request failed.';
    return {
      ok: false,
      message: `${detail} No task was changed.`,
    };
  }
}
