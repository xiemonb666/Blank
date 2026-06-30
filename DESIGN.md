---
version: alpha
name: Blank Learning Console
description: Fixed-viewport black-and-paper education workspace for concept decomposition, Socratic learning, and Feynman evidence.
colors:
  primary: "#111111"
  paper: "#F8F3E8"
  surface: "#FFFAF0"
  muted: "#656565"
  border: "#D8CEBC"
  accent: "#D4A373"
typography:
  app-title:
    fontFamily: "Noto Serif CJK SC, Source Han Serif SC, Songti SC, SimSun, serif"
    fontSize: 32px
    fontWeight: 800
    lineHeight: 1
    letterSpacing: 0
  section-title:
    fontFamily: "Noto Serif CJK SC, Source Han Serif SC, Songti SC, SimSun, serif"
    fontSize: 30px
    fontWeight: 800
    lineHeight: 1.08
    letterSpacing: 0
  body:
    fontFamily: "Noto Sans CJK SC, Source Han Sans SC, Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: 15px
    fontWeight: 500
    lineHeight: 1.55
    letterSpacing: 0
  label:
    fontFamily: "IBM Plex Mono, Space Mono, SFMono-Regular, Consolas, monospace"
    fontSize: 12px
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: 0
rounded:
  none: 0px
  sm: 0px
  md: 0px
  full: 999px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
components:
  shell:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.primary}"
    height: 100dvh
    padding: "{spacing.md}"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: "{spacing.lg}"
  control:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    height: 40px
  label:
    textColor: "{colors.muted}"
    typography: "{typography.label}"
  rule:
    backgroundColor: "{colors.border}"
    height: 1.5px
  accent-mark:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.primary}"
---

# Blank Learning Console

## Overview

Blank 的界面是一个固定视口的教育工作台，而不是长网页。它应该像一张能被反复使用的学习控制台：清晰、克制、密度高，但每个阶段只暴露当前任务需要的控件。主要情绪是可靠、专注、可追溯。

UI 必须服务“输入 -> 拆解 -> 学习 -> 输出 -> 证据”的闭环。任何长内容都进入分页、折叠或分步视图，不使用浏览器级滚动来隐藏结构问题。

## Colors

Blank 使用高对比黑白纸面体系，保留少量暖色作为研究端置信度和非关键提示。`primary` 是主要文字、边框和主操作色；纸色是所有界面背景；暖金只用于学术标记和置信度，不作为大面积主色。

## Typography

标题使用中文衬线字体，传达讲义和白板感；界面、按钮、正文使用无衬线字体；标签、指标、编号和状态使用等宽字体。字号不随视口宽度线性缩放，紧凑面板内不得使用 hero 级标题。

## Layout

布局固定在 `100dvh` 内，外层不滚动。桌面采用 topbar + rail + main stage + optional side panels；移动端采用 topbar + rail + stage 的单列工作台。长列表、研究数据和聊天历史必须通过分页、tab、stepper 或折叠层级呈现。

所有固定格式元素必须有稳定尺寸：rail 按钮、分页按钮、节点图、消息输入区、指标卡和问题队列不能因动态文本改变布局。

## Elevation & Depth

界面使用线框、轻微纸面背景和少量硬阴影表达层级。禁止使用装饰性渐变球、模糊光斑和卡片套卡片。悬浮控件必须有明确槽位，不能覆盖标题、表格或主内容。

## Shapes

默认形状为直角线框。圆角仅用于节点、雷达点和确有语义的圆形控件。按钮和卡片不使用大圆角。

## Components

按钮优先使用 lucide 图标加可访问标签；图标按钮必须有 `aria-label` 或 `title`。分段控件用于模式选择，stepper/pagination 用于长内容，details/accordion 用于低优先级说明。主操作按钮在每个 stage 中最多保留一个。

动效由 GSAP 管理：React 中使用 scoped `useGSAP`，复杂过渡使用 timeline，动效属性仅限 `transform` 和 `autoAlpha`。`prefers-reduced-motion: reduce` 下 duration 为 0。

## Do's and Don'ts

Do:
- 保持每个 stage 的第一屏信息完整、可操作。
- 用分页和切换替代原生滚动条。
- 让截图检查成为布局验收的一部分。
- 保持中文错误、说明和注释。

Don't:
- 不允许浏览器级滚动条或未设计的内部滚动条。
- 不允许浮动按钮覆盖内容。
- 不允许动画 `width`、`height`、`top`、`left`、`margin`、`padding`。
- 不允许为了容纳信息而把文字缩到难以阅读。
