"""
Pitboss v4 - Web UI

Local Flask app wrapping the v4 engine.
Launch: python app.py → browser opens to localhost:5000
"""

from __future__ import annotations
import argparse
import json
import logging
import os
import tempfile
import traceback
import webbrowser
from pathlib import Path
from threading import Timer

from flask import Flask, render_template, request, jsonify, send_file

# Import the pipeline functions
from run_pitboss import (
    run_docx_pipeline,
    run_gdoc_pipeline,
    run_check_only_gdoc,
    run_apply_selected_gdoc,
)
from core.finding import Finding

# Import check registry to list available checks
from core.check_base import get_registry


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

# Configure upload settings
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max
ALLOWED_EXTENSIONS = {'docx'}


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_available_checks() -> list[dict]:
    """Get list of all registered checks with metadata."""
    registry = get_registry()
    checks = []
    for check in registry.all_instances():
        meta = check.metadata
        checks.append({
            'name': meta.name,
            'display_name': meta.display_name,
            'category': meta.category,
            'check_type': str(meta.check_type),
            'description': meta.description,
            'enabled_by_default': meta.enabled_by_default,
        })
    return checks


@app.route('/')
def index():
    """Render the main form page."""
    checks = get_available_checks()
    return render_template('index.html', checks=checks)


@app.route('/run', methods=['POST'])
def run_pipeline():
    """Run the Pitboss pipeline on uploaded file or Google Doc."""
    try:
        # Get enabled checks from form
        # If checks_present marker exists: use selected checks (empty = run nothing)
        # If no marker (API/CLI call): run all checks
        enabled_checks = request.form.getlist('checks')
        if 'checks_present' not in request.form and not enabled_checks:
            enabled_checks = None  # No checkboxes in form → run all

        # Determine source type
        source_type = request.form.get('source_type', 'file')

        if source_type == 'gdoc':
            # Google Doc URL
            gdoc_url = request.form.get('gdoc_url', '').strip()
            if not gdoc_url:
                return jsonify({
                    'status': 'error',
                    'error': 'No Google Doc URL provided',
                    'error_type': 'ValidationError'
                }), 400

            logger.info(f"Running pipeline on Google Doc: {gdoc_url}")
            logger.info(f"Enabled checks: {enabled_checks or 'all'}")

            # Run gdoc pipeline
            corrected_url, auto_fix_count, comment_count, output_dir = run_gdoc_pipeline(
                gdoc_id_or_url=gdoc_url,
                brief_path=None,
                brand_id=None,
                enabled_checks=enabled_checks,
                skip_comments=True,  # Default off - Google orphans them anyway
            )

            # Read findings.json for detailed results (same as docx path)
            findings_path = output_dir / 'findings.json'
            findings_data = None
            if findings_path.exists():
                import json
                findings_data = json.loads(findings_path.read_text(encoding='utf-8'))

            return jsonify({
                'status': 'success',
                'corrected_url': corrected_url,
                'auto_fix_count': auto_fix_count,
                'comment_count': comment_count,
                'findings': findings_data,
                'output_dir': str(output_dir),
            })

        else:
            # File upload
            if 'article' not in request.files:
                return jsonify({
                    'status': 'error',
                    'error': 'No file uploaded',
                    'error_type': 'ValidationError'
                }), 400

            file = request.files['article']
            if file.filename == '':
                return jsonify({
                    'status': 'error',
                    'error': 'No file selected',
                    'error_type': 'ValidationError'
                }), 400

            if not allowed_file(file.filename):
                return jsonify({
                    'status': 'error',
                    'error': 'Invalid file type. Only .docx files are allowed.',
                    'error_type': 'ValidationError'
                }), 400

            # Save uploaded file to temp location
            # Windows fix: create temp path, close handle, THEN save
            tmp_fd, tmp_name = tempfile.mkstemp(suffix='.docx')
            os.close(tmp_fd)  # Close immediately - Windows won't allow double-open
            tmp_path = Path(tmp_name)
            file.save(tmp_path)

            try:
                logger.info(f"Running pipeline on: {file.filename}")
                logger.info(f"Enabled checks: {enabled_checks or 'all'}")

                corrected_path, comments_path, summary_path = run_docx_pipeline(
                    article_path=tmp_path,
                    brief_path=None,
                    brand_id=None,
                    enabled_checks=enabled_checks,
                )

                # Read the summary for display
                summary_text = summary_path.read_text(encoding='utf-8')

                # Read findings.json for detailed results
                findings_path = corrected_path.parent / 'findings.json'
                findings_data = None
                if findings_path.exists():
                    import json
                    findings_data = json.loads(findings_path.read_text(encoding='utf-8'))

                return jsonify({
                    'status': 'success',
                    'corrected_path': str(corrected_path),
                    'comments_path': str(comments_path),
                    'summary_path': str(summary_path),
                    'findings_path': str(findings_path) if findings_path.exists() else None,
                    'summary_text': summary_text,
                    'findings': findings_data,
                    'output_dir': str(corrected_path.parent),
                })

            finally:
                # Clean up temp file
                if tmp_path.exists():
                    tmp_path.unlink()

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'error',
            'error': str(e),
            'error_type': type(e).__name__,
            'traceback': traceback.format_exc() if app.debug else None,
        }), 500


# =============================================================================
# TWO-PHASE FLOW (UI-as-review-surface)
# =============================================================================

@app.route('/check', methods=['POST'])
def check_only():
    """
    Phase 1: Run checks on Google Doc, return all findings.
    NO auto-apply, NO doc writing. User reviews findings in UI.
    """
    try:
        # Get enabled checks from form
        enabled_checks = request.form.getlist('checks')
        if 'checks_present' not in request.form and not enabled_checks:
            enabled_checks = None  # No checkboxes in form → run all

        gdoc_url = request.form.get('gdoc_url', '').strip()
        if not gdoc_url:
            return jsonify({
                'status': 'error',
                'error': 'No Google Doc URL provided',
                'error_type': 'ValidationError'
            }), 400

        # Handle brief file upload (optional)
        brief_path = None
        if 'brief' in request.files:
            brief_file = request.files['brief']
            if brief_file.filename:
                # Windows fix: create temp path, close handle, THEN save
                suffix = Path(brief_file.filename).suffix
                tmp_fd, tmp_name = tempfile.mkstemp(suffix=suffix)
                os.close(tmp_fd)  # Close immediately - Windows won't allow double-open
                brief_path = Path(tmp_name)
                brief_file.save(brief_path)
                logger.info(f"Brief uploaded: {brief_file.filename}")

        logger.info(f"[Phase 1] Running checks on: {gdoc_url}")
        logger.info(f"Enabled checks: {enabled_checks or 'all'}")
        logger.info(f"Brief: {brief_path or 'none'}")

        try:
            # Run Phase 1
            result = run_check_only_gdoc(
                gdoc_id_or_url=gdoc_url,
                brief_path=brief_path,
                brand_id=None,
                enabled_checks=enabled_checks,
            )
        finally:
            # Clean up brief temp file
            if brief_path and brief_path.exists():
                brief_path.unlink()

        # Read full findings.json for response
        findings_path = result.output_dir / 'findings.json'
        findings_data = None
        if findings_path.exists():
            findings_data = json.loads(findings_path.read_text(encoding='utf-8'))

        # Build findings list for UI (mark advisory-only findings)
        findings_for_ui = []
        for f in result.findings:
            findings_for_ui.append({
                'finding_id': f.finding_id,
                'check_name': f.check_name,
                'severity': f.severity,
                'auto_applicable': f.auto_applicable,
                'has_proposed_text': f.proposed_text is not None and f.proposed_text != f.original_text,
                'original_text': f.original_text[:100] + '...' if f.original_text and len(f.original_text) > 100 else f.original_text,
                'proposed_text': f.proposed_text[:100] + '...' if f.proposed_text and len(f.proposed_text) > 100 else f.proposed_text,
                'reasoning': f.reasoning,
                'location': {
                    'paragraph_index': f.location.paragraph_index,
                    'section_title': f.location.section_title,
                    'element_type': f.location.element_type,
                },
            })

        return jsonify({
            'status': 'success',
            'phase': 1,
            'doc_id': result.doc_id,
            'doc_title': result.document.title,
            'word_count': len(result.document.full_text().split()),
            'total_findings': len(result.findings),
            'findings': findings_for_ui,
            'findings_raw': findings_data,  # Full data for Phase 2
            'output_dir': str(result.output_dir),
        })

    except Exception as e:
        logger.error(f"Phase 1 check failed: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'error',
            'error': str(e),
            'error_type': type(e).__name__,
            'traceback': traceback.format_exc() if app.debug else None,
        }), 500


@app.route('/apply', methods=['POST'])
def apply_selected():
    """
    Phase 2: Apply user-selected findings to Google Doc.
    Re-reads doc fresh, applies only selected findings, reports skipped/downgraded.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'error': 'No JSON body provided',
                'error_type': 'ValidationError'
            }), 400

        gdoc_url = data.get('gdoc_url', '').strip()
        if not gdoc_url:
            return jsonify({
                'status': 'error',
                'error': 'No Google Doc URL provided',
                'error_type': 'ValidationError'
            }), 400

        selected_ids = data.get('selected_ids', [])
        if not selected_ids:
            return jsonify({
                'status': 'error',
                'error': 'No findings selected',
                'error_type': 'ValidationError'
            }), 400

        # Reconstruct findings from Phase 1 data
        findings_raw = data.get('findings_raw', {})
        findings_list = findings_raw.get('findings', [])
        findings = [Finding.from_dict(f) for f in findings_list]

        output_dir = data.get('output_dir')
        if output_dir:
            output_dir = Path(output_dir)

        logger.info(f"[Phase 2] Applying {len(selected_ids)} selected findings to: {gdoc_url}")

        # Run Phase 2
        result = run_apply_selected_gdoc(
            gdoc_id_or_url=gdoc_url,
            findings=findings,
            selected_ids=selected_ids,
            output_dir=output_dir,
        )

        return jsonify({
            'status': 'success',
            'phase': 2,
            'applied_count': len(result.applied),
            'applied': [f.finding_id for f in result.applied],
            'skipped_count': len(result.skipped),
            'skipped': [
                {
                    'finding_id': s.finding_id,
                    'check_name': s.check_name,
                    'reason': s.reason,
                    'detail': s.detail,
                    'original_text': s.original_text[:50] + '...' if s.original_text and len(s.original_text) > 50 else s.original_text,
                    'actual_text': s.actual_text[:50] + '...' if s.actual_text and len(s.actual_text) > 50 else s.actual_text,
                }
                for s in result.skipped
            ],
            'downgraded_count': len(result.downgraded),
            'downgraded': [
                {
                    'finding_id': d.finding_id,
                    'check_name': d.check_name,
                    'reason': d.reason,
                    'detail': d.detail,
                    'conflicting_with': d.conflicting_with,
                }
                for d in result.downgraded
            ],
            'corrected_url': result.corrected_url,
            'output_dir': str(result.output_dir),
        })

    except Exception as e:
        logger.error(f"Phase 2 apply failed: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'error',
            'error': str(e),
            'error_type': type(e).__name__,
            'traceback': traceback.format_exc() if app.debug else None,
        }), 500


@app.route('/download/<path:filepath>')
def download_file(filepath: str):
    """Download a result file."""
    try:
        path = Path(filepath)
        if not path.exists():
            return jsonify({'error': 'File not found'}), 404

        # Security: only allow files in output_runs directory
        if 'output_runs' not in str(path):
            return jsonify({'error': 'Access denied'}), 403

        return send_file(
            path,
            as_attachment=True,
            download_name=path.name,
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def open_browser(port: int):
    """Open browser after short delay."""
    webbrowser.open(f'http://localhost:{port}')


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description='Pitboss v4 Web UI')
    parser.add_argument('--port', type=int, default=5000, help='Port to run on')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--open', action='store_true', help='Auto-open browser')
    args = parser.parse_args()

    if args.open:
        # Open browser after 1 second delay
        Timer(1.0, open_browser, args=[args.port]).start()

    print(f"\n{'='*50}")
    print("PITBOSS v4 WEB UI")
    print(f"{'='*50}")
    print(f"Open in browser: http://localhost:{args.port}")
    print(f"{'='*50}\n")

    app.run(
        host='127.0.0.1',
        port=args.port,
        debug=args.debug,
    )


if __name__ == '__main__':
    main()
