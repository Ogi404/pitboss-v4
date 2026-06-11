# Pitboss v4

A ground-up rebuild of the Pitboss editorial automation system.

## Architecture

See [PITBOSS-V4-ARCHITECTURE.md](./PITBOSS-V4-ARCHITECTURE.md) for the full design document.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/
```

## Project Structure

```
pitboss_v_4/
├── core/                    # The three frozen contracts
│   ├── document.py          # Document model (Contract #1)
│   ├── finding.py           # Finding dataclass (Contract #2)
│   ├── check_base.py        # Check interface (Contract #3)
│   └── standards_engine.py  # Standards loading with inheritance
├── brands/                  # Brand configuration YAML
│   ├── _defaults.yaml       # Company-wide standards
│   └── vave.yaml            # Example brand profile
├── deterministic/           # Deterministic checks (the 95%)
├── judgment/                # LLM-assisted checks (the 5%)
├── ingest/                  # Document ingestion
├── output/                  # Output builders
├── factcheck/               # Fact-checking subsystem
├── learning/                # Learning loop
├── corpora/                 # Approved article corpora
└── tests/                   # Test suite
```

## Phase 0: Core Scaffolding

This is the Phase 0 implementation containing:

1. **Three Frozen Contracts** - The stable interfaces everything else depends on
2. **Standards Engine** - Configuration loading with inheritance
3. **Default Standards** - General Writing Requirements encoded as YAML
4. **Test Suite** - Comprehensive tests for all contracts

## License

Proprietary
