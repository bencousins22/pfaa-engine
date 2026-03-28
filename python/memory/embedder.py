#!/usr/bin/env python3
"""
Persistent embedding server for Aussie Agents.
Runs as a long-lived subprocess — loads sentence-transformers ONCE at startup,
then processes embed requests via stdin/stdout JSON lines forever.

Protocol:
  Ready signal → stdout: {"status": "ready", "dim": 768}
  Request  ← stdin:  {"texts": ["query1", "query2"]}
  Response → stdout: {"vectors": [[0.1, 0.2, ...], ...]}

Launch with PYTHON_GIL=0 for true parallel encoding on free-threaded builds:
  PYTHON_GIL=0 python3 embedder.py

Usage: python3 embedder.py [--model sentence-transformers/all-mpnet-base-v2]
"""

import os
import sys
import json
import signal
import argparse

# Ensure GIL-free execution when available (Python 3.13+ free-threaded builds)
if 'PYTHON_GIL' not in os.environ:
    os.environ['PYTHON_GIL'] = '0'


def main():
    parser = argparse.ArgumentParser(
        description='Persistent embedding subprocess — loads model once, stays warm forever.',
    )
    parser.add_argument('--model', default='sentence-transformers/all-mpnet-base-v2')
    parser.add_argument('--batch-size', type=int, default=64,
                        help='Encoding batch size for large inputs')
    args = parser.parse_args()

    # Ignore SIGTERM/SIGHUP to stay alive — parent must send SIGKILL to force exit
    signal.signal(signal.SIGTERM, lambda *_: None)
    signal.signal(signal.SIGHUP, lambda *_: None)

    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(args.model)
        dim = model.get_sentence_embedding_dimension()
        sys.stderr.write(f'[embedder] loaded {args.model} dim={dim} GIL={os.environ.get("PYTHON_GIL", "1")}\n')
        sys.stderr.flush()
    except ImportError:
        # Fallback: return zero vectors if sentence-transformers not installed
        sys.stderr.write('[embedder] sentence-transformers not available, using zero vectors\n')
        sys.stderr.flush()
        dim = 768
        model = None

    # Signal ready — consumers wait for this before sending requests
    sys.stdout.write(json.dumps({'status': 'ready', 'dim': dim}) + '\n')
    sys.stdout.flush()

    # Main loop — never exits, stays warm for the entire session
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                # stdin closed (parent died) — restart stdin wait
                # This keeps the process alive even if the pipe breaks briefly
                break
            line = line.strip()
            if not line:
                continue

            req = json.loads(line)
            texts = req.get('texts', [])

            if not texts:
                sys.stdout.write(json.dumps({'vectors': []}) + '\n')
                sys.stdout.flush()
                continue

            if model is not None:
                vecs = model.encode(
                    texts,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                    batch_size=args.batch_size,
                )
                sys.stdout.write(json.dumps({'vectors': vecs.tolist()}) + '\n')
            else:
                sys.stdout.write(json.dumps({'vectors': [[0.0] * dim for _ in texts]}) + '\n')
            sys.stdout.flush()

        except json.JSONDecodeError as e:
            sys.stdout.write(json.dumps({'error': f'Invalid JSON: {e}'}) + '\n')
            sys.stdout.flush()
        except Exception as e:
            sys.stdout.write(json.dumps({'error': str(e)}) + '\n')
            sys.stdout.flush()
            # Never exit on errors — stay warm


if __name__ == '__main__':
    main()
