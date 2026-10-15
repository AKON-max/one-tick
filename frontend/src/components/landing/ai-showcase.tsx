"use client";

import { motion } from "motion/react";
import {
  ArrowsClockwise,
  Bell,
  Books,
  Brain,
  ChatCircleDots,
  CheckCircle,
  Gauge,
  Lightning,
  PaperPlaneTilt,
  Robot,
  Sparkle,
} from "@phosphor-icons/react";

/** 雨宝的能力（每一条都对应真实后端实现，见 app/ai 与 app/routers/ai.py） */
const abilities = [
  {
    icon: Brain,
    title: "先读数据，再开口",
    copy: "回答前会读你的打卡、连续天数、专注分钟、计划进度与长期记忆，而不是给一段通用建议。",
  },
  {
    icon: Lightning,
    title: "十余个真实工具",
    copy: "查统计、读计划、拆任务、改任务状态、管待办、检索知识库——它能真的动手改你的数据。",
  },
  {
    icon: Books,
    title: "知识库 RAG 问答",
    copy: "上传 md / txt / PDF / docx，切块向量化后用 pgvector 检索并重排，回答标注来源。",
  },
  {
    icon: Bell,
    title: "每日 / 每周自主学习",
    copy: "后台按「观察 → 分析 → 计划 → 执行」跑完整流程，把提醒、报告与任务调整推送到通知中心。",
  },
  {
    icon: ChatCircleDots,
    title: "群聊里的 AI 群友",
    copy: "在聊天室 @温柔宝 或 @嘴欠宝，两个性格不同的伙伴会实时接话。",
  },
  {
    icon: Gauge,
    title: "模型池兜底，用量透明",
    copy: "多模型自动降级 + 每日 token 额度（雨宝精力条），高峰时也不会突然沉默。",
  },
];

/** AI 已经渗透到的环节 */
const touchpoints = [
  { page: "计划页", copy: "文档粘进来就拆成可打勾的任务；文档改了会提示「任务过期」，一键重新拆解。" },
  { page: "文档工作台", copy: "框选任意段落问 AI，让它解释、总结或给出改写建议。" },
  { page: "聊天室", copy: "@雨宝 把它拉进群聊，边聊边问。" },
  { page: "通知中心", copy: "AI 生成的提醒、报告与鼓励，按天推给你。" },
  { page: "统计页", copy: "雨宝精力条，AI 用量一眼看清。" },
];

const generatedTasks = ["整理错题清单 · 25 分钟", "精读英语长难句 3 句", "复盘虚拟 DOM 笔记"];

export function AiShowcase() {
  return (
    <section id="ai" className="relative border-y border-white/10 bg-background/88 px-4 py-20 text-white backdrop-blur-2xl md:px-8 md:py-28">
      <div className="mx-auto max-w-7xl">
        {/* 标题 */}
        <div className="grid gap-8 md:grid-cols-[0.9fr_1.1fr] md:items-end">
          <div>
            <p className="text-sm font-semibold text-primary">AI 不是外挂，是住在工作台里的伙伴</p>
            <h2 className="mt-3 text-3xl font-semibold leading-tight md:text-5xl">
              雨宝读懂你的数据，
              <br />
              再把<span className="text-primary">下一步</span>交给你
            </h2>
          </div>
          <p className="max-w-2xl text-base leading-relaxed text-white/58 md:text-lg">
            它先看你的真实数据，再决定该做什么：把一份计划拆成今天能做完的任务、在你偏离节奏时提醒一句、
            周末写一份复盘报告，或者翻出你上传的资料回答问题。对话只是入口，动手才是重点。
          </p>
        </div>

        {/* 左：真实对话形态；右：能力清单 */}
        <div className="mt-14 grid gap-6 lg:grid-cols-[1.05fr_0.95fr]">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.6 }}
            className="flex flex-col rounded-lg border border-white/14 bg-background/74 p-6 shadow-[0_32px_90px_rgba(0,0,0,0.28)] sm:p-8"
          >
            <div className="flex items-center gap-3">
              <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary/14 text-primary">
                <Robot className="size-5" weight="duotone" />
              </span>
              <div>
                <h3 className="text-lg font-semibold">雨宝：会读数据，也会动手</h3>
                <p className="mt-0.5 text-[11px] text-white/35">流式回复 · 可随时打断 · 深度思考开关</p>
              </div>
            </div>

            {/* 对话示意 */}
            <div className="mt-7 flex-1 rounded-lg border border-white/12 bg-black/20 p-4 sm:p-5">
              <div className="flex justify-end">
                <p className="max-w-[88%] rounded-xl rounded-br-sm bg-primary/16 px-4 py-2.5 text-[13px] leading-6 text-white/85">
                  帮我把「暑期能力进阶」拆成这周能做完的任务
                </p>
              </div>

              <div className="mt-4 flex items-center gap-2 text-[11px] text-white/35">
                <ArrowsClockwise className="size-3.5 shrink-0 text-primary" />
                <span>正在读取：学习统计 · 我的计划 · 今日任务</span>
              </div>

              <div className="mt-4 flex items-start gap-3">
                <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/14 text-primary">
                  <Sparkle className="size-3.5" weight="fill" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] leading-6 text-white/72">
                    拆好了。按你最近 6 天的专注节奏，这周先攻这 3 件事，每件都压在 25 分钟内，做完直接在计划里打勾就行。
                  </p>
                  <div className="mt-3 space-y-2">
                    {generatedTasks.map((task) => (
                      <div
                        key={task}
                        className="flex items-center gap-2.5 rounded-md border border-white/10 bg-white/[0.03] px-3 py-2"
                      >
                        <CheckCircle className="size-4 shrink-0 text-white/24" />
                        <span className="text-xs text-white/70">{task}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-5 flex h-11 items-center gap-3 rounded-lg border border-white/12 bg-white/[0.035] px-3">
              <span className="flex-1 text-xs text-white/28">问问雨宝下一步做什么…</span>
              <PaperPlaneTilt className="size-4 text-primary" weight="fill" />
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.6, delay: 0.08 }}
            className="flex flex-col justify-between gap-6 rounded-lg border border-white/14 bg-background/74 p-6 shadow-[0_32px_90px_rgba(0,0,0,0.28)] sm:p-8"
          >
            {abilities.map(({ icon: Icon, title, copy }) => (
              <div key={title} className="flex items-start gap-4">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/12 text-primary">
                  <Icon className="size-4.5" weight="duotone" />
                </span>
                <div>
                  <p className="text-sm font-semibold">{title}</p>
                  <p className="mt-1 text-xs leading-5 text-white/45">{copy}</p>
                </div>
              </div>
            ))}
          </motion.div>
        </div>

        {/* AI 已经渗透到的环节 */}
        <div className="mt-10 grid gap-px border-y border-white/10 bg-white/10 sm:grid-cols-2 lg:grid-cols-5">
          {touchpoints.map(({ page, copy }) => (
            <div key={page} className="bg-background px-5 py-5">
              <p className="text-sm font-semibold text-primary">{page}</p>
              <p className="mt-1.5 text-[11px] leading-4 text-white/40">{copy}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
