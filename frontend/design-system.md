# Agrawal Estate Planner - Design System

> Inspired by Robinhood's modern, clean aesthetic with a sophisticated family wealth management twist.

---

## 🎨 Brand Philosophy

**Core Principles:**
- **Clarity First**: Financial data should be immediately understandable
- **Confident Minimalism**: Every element earns its place
- **Trustworthy & Modern**: Professional enough for serious wealth management, modern enough to feel current
- **Dark Mode Primary**: Easier on eyes for data-heavy dashboards, premium feel

---

## 🎨 Color Palette

### Primary Colors (Dark Theme - Default)

```css
/* Base */
--color-bg-primary: #0D0D0D;        /* Near black - main background */
--color-bg-secondary: #1A1A1A;      /* Cards, elevated surfaces */
--color-bg-tertiary: #242424;       /* Inputs, hover states */
--color-bg-elevated: #2D2D2D;       /* Modals, dropdowns */

/* Text */
--color-text-primary: #FFFFFF;      /* Primary text */
--color-text-secondary: #A3A3A3;    /* Secondary/muted text */
--color-text-tertiary: #737373;     /* Disabled, hints */

/* Accent - "Agrawal Green" (inspired by Robin Neon) */
--color-accent: #00D632;            /* Primary accent - vibrant green */
--color-accent-hover: #00E639;      /* Hover state */
--color-accent-muted: #00D63220;    /* Background tint */

/* Semantic Colors */
--color-positive: #00D632;          /* Gains, success */
--color-negative: #FF5A5A;          /* Losses, errors */
--color-warning: #FFB800;           /* Warnings, alerts */
--color-info: #00A3FF;              /* Information */

/* Chart Colors */
--color-chart-1: #00D632;           /* Primary (green) */
--color-chart-2: #00A3FF;           /* Blue */
--color-chart-3: #A855F7;           /* Purple */
--color-chart-4: #FFB800;           /* Gold */
--color-chart-5: #FF5A5A;           /* Red */
--color-chart-6: #06B6D4;           /* Cyan */
```

### Light Theme (Optional)

```css
/* Base */
--color-bg-primary: #FFFFFF;
--color-bg-secondary: #F5F5F5;
--color-bg-tertiary: #E5E5E5;
--color-bg-elevated: #FFFFFF;

/* Text */
--color-text-primary: #0D0D0D;
--color-text-secondary: #525252;
--color-text-tertiary: #A3A3A3;
```

---

## 📝 Typography

### Font Families

```css
/* Primary - Clean geometric sans-serif (similar to Capsule Sans) */
--font-primary: 'Outfit', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;

/* Display - For large headings, adds personality */
--font-display: 'Space Grotesk', 'Outfit', sans-serif;

/* Mono - For numbers, financial data */
--font-mono: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;
```

### Type Scale

```css
/* Font Sizes */
--text-xs: 0.75rem;     /* 12px - Labels, captions */
--text-sm: 0.875rem;    /* 14px - Secondary text */
--text-base: 1rem;      /* 16px - Body text */
--text-lg: 1.125rem;    /* 18px - Large body */
--text-xl: 1.25rem;     /* 20px - Small headings */
--text-2xl: 1.5rem;     /* 24px - Section headings */
--text-3xl: 1.875rem;   /* 30px - Page headings */
--text-4xl: 2.25rem;    /* 36px - Large headings */
--text-5xl: 3rem;       /* 48px - Hero numbers */
--text-6xl: 3.75rem;    /* 60px - Dashboard totals */

/* Font Weights */
--font-normal: 400;
--font-medium: 500;
--font-semibold: 600;
--font-bold: 700;

/* Line Heights */
--leading-tight: 1.1;   /* Headings */
--leading-snug: 1.3;    /* Subheadings */
--leading-normal: 1.5;  /* Body text */
--leading-relaxed: 1.7; /* Long-form content */
```

### Typography Usage

| Element | Font | Size | Weight | Color |
|---------|------|------|--------|-------|
| Dashboard Total | Display | 6xl | Bold | Primary |
| Page Title | Display | 3xl | Semibold | Primary |
| Section Header | Primary | 2xl | Semibold | Primary |
| Card Title | Primary | lg | Medium | Primary |
| Body Text | Primary | base | Normal | Secondary |
| Financial Numbers | Mono | varies | Medium | Primary |
| Labels | Primary | sm | Medium | Tertiary |
| Gain/Loss | Mono | varies | Semibold | Positive/Negative |

---

## 📐 Spacing System

```css
/* Base unit: 4px */
--space-0: 0;
--space-1: 0.25rem;   /* 4px */
--space-2: 0.5rem;    /* 8px */
--space-3: 0.75rem;   /* 12px */
--space-4: 1rem;      /* 16px */
--space-5: 1.25rem;   /* 20px */
--space-6: 1.5rem;    /* 24px */
--space-8: 2rem;      /* 32px */
--space-10: 2.5rem;   /* 40px */
--space-12: 3rem;     /* 48px */
--space-16: 4rem;     /* 64px */
--space-20: 5rem;     /* 80px */
--space-24: 6rem;     /* 96px */
```

---

## 🔲 Border Radius

```css
--radius-sm: 4px;     /* Buttons, inputs */
--radius-md: 8px;     /* Cards, small containers */
--radius-lg: 12px;    /* Large cards, modals */
--radius-xl: 16px;    /* Feature cards */
--radius-2xl: 24px;   /* Hero sections */
--radius-full: 9999px; /* Pills, avatars */
```

---

## 🌑 Shadows & Elevation

```css
/* Dark theme shadows (subtle glow effect) */
--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.5);
--shadow-md: 0 4px 6px rgba(0, 0, 0, 0.4);
--shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.3);
--shadow-xl: 0 20px 25px rgba(0, 0, 0, 0.25);

/* Accent glow (for hover states, focus) */
--shadow-glow: 0 0 20px rgba(0, 214, 50, 0.3);
--shadow-glow-strong: 0 0 30px rgba(0, 214, 50, 0.5);
```

---

## 🎭 Component Patterns

### Cards

```css
.card {
  background: var(--color-bg-secondary);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.card:hover {
  border-color: rgba(255, 255, 255, 0.1);
  background: var(--color-bg-tertiary);
}
```

### Buttons

```css
/* Primary Button */
.btn-primary {
  background: var(--color-accent);
  color: #000000;
  font-weight: var(--font-semibold);
  padding: var(--space-3) var(--space-6);
  border-radius: var(--radius-sm);
  transition: all 0.2s ease;
}

.btn-primary:hover {
  background: var(--color-accent-hover);
  box-shadow: var(--shadow-glow);
}

/* Secondary Button */
.btn-secondary {
  background: transparent;
  color: var(--color-text-primary);
  border: 1px solid rgba(255, 255, 255, 0.2);
  padding: var(--space-3) var(--space-6);
  border-radius: var(--radius-sm);
}

.btn-secondary:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}
```

### Data Display

```css
/* Large financial number */
.value-display {
  font-family: var(--font-mono);
  font-size: var(--text-5xl);
  font-weight: var(--font-bold);
  letter-spacing: -0.02em;
}

/* Percentage change */
.change-positive {
  color: var(--color-positive);
}

.change-negative {
  color: var(--color-negative);
}

/* With background pill */
.change-pill {
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

.change-pill.positive {
  background: rgba(0, 214, 50, 0.15);
  color: var(--color-positive);
}

.change-pill.negative {
  background: rgba(255, 90, 90, 0.15);
  color: var(--color-negative);
}
```

---

## 📊 Data Visualization

### Chart Guidelines

1. **Colors**: Use chart color palette in order, maintain consistency across app
2. **Grid Lines**: Subtle, use `rgba(255, 255, 255, 0.05)`
3. **Axis Labels**: Use `--color-text-tertiary`, `--text-xs`
4. **Tooltips**: Dark elevated surface with accent border
5. **Animations**: Smooth entry animations (300ms ease-out)

### Recommended Libraries
- **Charts**: Recharts or Victory (React-friendly, customizable)
- **Tables**: TanStack Table (powerful, headless)

---

## 🎬 Motion & Animation

```css
/* Timing Functions */
--ease-default: cubic-bezier(0.4, 0, 0.2, 1);
--ease-in: cubic-bezier(0.4, 0, 1, 1);
--ease-out: cubic-bezier(0, 0, 0.2, 1);
--ease-bounce: cubic-bezier(0.34, 1.56, 0.64, 1);

/* Durations */
--duration-fast: 150ms;
--duration-normal: 200ms;
--duration-slow: 300ms;
--duration-slower: 500ms;

/* Common Animations */
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from { 
    opacity: 0; 
    transform: translateY(10px); 
  }
  to { 
    opacity: 1; 
    transform: translateY(0); 
  }
}

@keyframes scaleIn {
  from { 
    opacity: 0; 
    transform: scale(0.95); 
  }
  to { 
    opacity: 1; 
    transform: scale(1); 
  }
}

/* Number counting animation for totals */
@keyframes countUp {
  from { opacity: 0.5; }
  to { opacity: 1; }
}
```

### Animation Guidelines

1. **Page Transitions**: Fade + slight slide (300ms)
2. **Card Hover**: Scale 1.01, subtle shadow increase (200ms)
3. **Button Press**: Scale 0.98 (100ms)
4. **Number Changes**: Brief flash/pulse when values update
5. **Loading States**: Skeleton screens with subtle shimmer
6. **Stagger**: Cards load with 50ms delay between each

---

## 📱 Responsive Breakpoints

```css
--breakpoint-sm: 640px;   /* Mobile landscape */
--breakpoint-md: 768px;   /* Tablet */
--breakpoint-lg: 1024px;  /* Desktop */
--breakpoint-xl: 1280px;  /* Large desktop */
--breakpoint-2xl: 1536px; /* Ultra-wide */
```

---

## 🧩 Layout Patterns

### Dashboard Grid
```
┌─────────────────────────────────────────────┐
│  Net Worth (Hero)                           │
├─────────────────┬───────────────────────────┤
│  Quick Stats    │  Portfolio Chart          │
│  (4 cards)      │                           │
├─────────────────┴───────────────────────────┤
│  Holdings / Recent Activity (Table)         │
└─────────────────────────────────────────────┘
```

### Sidebar Navigation
- Fixed left sidebar (280px)
- Collapsible to icons only (64px)
- Logo at top
- Navigation items with icons
- User/settings at bottom

---

## 🖼️ Iconography

**Style**: 
- Stroke-based, 1.5px weight
- Rounded corners
- Consistent 24x24 grid

**Recommended**: 
- Lucide Icons (open source, consistent)
- Heroicons (alternative)

---

## 📁 File Structure for Styles

```
frontend/src/
├── styles/
│   ├── tokens.css        /* CSS custom properties */
│   ├── globals.css       /* Reset, base styles */
│   ├── typography.css    /* Type system */
│   └── animations.css    /* Keyframes, transitions */
├── components/
│   └── ui/               /* Reusable UI components */
└── app/
    └── layout.tsx        /* Root layout with providers */
```

---

## 🎯 Key Design Decisions

1. **Dark mode first** - Matches Robinhood's premium feel, easier on eyes for financial data
2. **Monospace for numbers** - Improves scannability of financial figures
3. **Green accent** - Universal "money/growth" association
4. **Minimal borders** - Use background color differentiation instead
5. **Generous whitespace** - Let data breathe, reduce cognitive load
6. **Consistent 8px grid** - All spacing multiples of 8 (or 4 for tight spaces)

---

*Design System v1.0 - Agrawal Family Apps*















