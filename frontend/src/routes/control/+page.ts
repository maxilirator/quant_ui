import type { PageLoad } from './$types';
import { listControlTasks, listControlJobs, listControlCSVs } from '$lib/api/client';
import type { ControlTask, ControlJob, ControlCSVFile } from '$lib/api/types';

export const load: PageLoad = async ({ fetch }) => {
    try {
        const [tasks, jobs, csvs] = await Promise.all([
            listControlTasks(fetch),
            listControlJobs(fetch),
            listControlCSVs(fetch)
        ]);
        return { tasks, jobs, csvs, fetchErrors: null };
    } catch (e: any) {
        return { tasks: [] as ControlTask[], jobs: [] as ControlJob[], csvs: [] as ControlCSVFile[], fetchErrors: String(e) };
    }
};
