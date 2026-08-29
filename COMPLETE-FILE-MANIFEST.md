# Complete Guidance Package Manifest

The archive is complete only when all paths below exist after extraction.

```text
project-root/
├── CLAUDE.md
├── PACKAGE-README.md
├── COMPLETE-FILE-MANIFEST.md
├── .gitignore
└── .claude/
    └── skills/
        ├── assessment-quality-gate/
        │   ├── SKILL.md
        │   └── references/
        │       └── acceptance-matrix.md
        ├── factory-digital-twin/
        │   ├── SKILL.md
        │   └── references/
        │       └── simulator-specification.md
        ├── factory-manager-dashboard/
        │   ├── SKILL.md
        │   └── references/
        │       └── dashboard-specification.md
        ├── factory-system-architecture/
        │   ├── SKILL.md
        │   └── references/
        │       └── api-and-data-specification.md
        ├── sensor-risk-modeling/
        │   ├── SKILL.md
        │   └── references/
        │       └── model-specification.md
        └── vision-worker-safety/
            ├── SKILL.md
            └── references/
                └── model-specification.md
```

Expected totals inside `project-root`:

- 6 skill directories;
- 6 `SKILL.md` files;
- 6 reference specification files;
- 4 root guidance/configuration files.

The `.claude` directory begins with a dot and may be hidden by some file browsers. Preserve its name when copying `project-root` into the repository.
