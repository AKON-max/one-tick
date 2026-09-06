"use server";

// ============================================================
// 计划 Server Action（薄封装）
// 业务逻辑已迁移到 Python FastAPI（/api/plans），
// 这里只负责转发请求 + 控制页面缓存失效，调用方无需改动。
// ============================================================

import { revalidatePath } from "next/cache";
import type { ActionResult } from "@/types";
import { apiFetch } from "@/lib/server-api";

interface PlanPayload {
  id: string;
}

/** 新建一个空白计划并返回 planId（前端随即跳进 studio） */
export async function createBlankPlan(): Promise<ActionResult<{ planId: string }>> {
  try {
    const res = await apiFetch<{ success: boolean; plan: PlanPayload }>("/api/plans", {
      method: "POST",
      body: JSON.stringify({ name: "未命名计划" }),
    });
    if (!res.success || !res.plan?.id) return { success: false, error: "创建计划失败" };
    return { success: true, data: { planId: res.plan.id } };
  } catch (error) {
    console.error("[createBlankPlan] 失败:", error);
    return {
      success: false,
      error: error instanceof Error ? error.message : "创建计划失败，请稍后重试",
    };
  }
}

export async function createPlan(formData: FormData): Promise<ActionResult> {
  try {
    const name = formData.get("name") as string;
    const startDate = formData.get("startDate")
      ? new Date(formData.get("startDate") as string).toISOString()
      : null;

    await apiFetch("/api/plans", {
      method: "POST",
      body: JSON.stringify({
        name,
        description: (formData.get("description") as string) || null,
        goal: (formData.get("goal") as string) || null,
        startDate,
      }),
    });

    revalidatePath("/plans");
    return { success: true };
  } catch (error) {
    console.error("[createPlan] 失败:", error);
    return {
      success: false,
      error: error instanceof Error ? error.message : "创建计划失败，请稍后重试",
    };
  }
}

export async function updatePlan(planId: string, formData: FormData): Promise<ActionResult> {
  try {
    const startDate = formData.get("startDate")
      ? new Date(formData.get("startDate") as string).toISOString()
      : null;

    await apiFetch(`/api/plans/${planId}`, {
      method: "PATCH",
      body: JSON.stringify({
        name: (formData.get("name") as string) || undefined,
        description: (formData.get("description") as string) || null,
        goal: (formData.get("goal") as string) || null,
        startDate,
      }),
    });

    revalidatePath("/plans");
    return { success: true };
  } catch (error) {
    console.error("[updatePlan] 失败:", error);
    return {
      success: false,
      error: error instanceof Error ? error.message : "更新计划失败，请稍后重试",
    };
  }
}

export async function deletePlan(planId: string): Promise<ActionResult> {
  try {
    await apiFetch(`/api/plans/${planId}`, { method: "DELETE" });
    revalidatePath("/plans");
    return { success: true };
  } catch (error) {
    console.error("[deletePlan] 失败:", error);
    return {
      success: false,
      error: error instanceof Error ? error.message : "删除计划失败，请稍后重试",
    };
  }
}
