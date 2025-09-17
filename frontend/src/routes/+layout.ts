import type { Load } from '@sveltejs/kit';
import { getControlMeta } from '$lib/api/client';

export const load: Load = async ({ fetch }) => {
    try {
        const meta = await getControlMeta(fetch);
        return { controlMeta: meta };
    } catch {
        return { controlMeta: { dev_mode: false, version: 'unknown' } };
    }
};
