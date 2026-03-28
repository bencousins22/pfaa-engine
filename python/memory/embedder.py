#!/usr/bin/env python3
"""
Persistent embedding server for PFAA.
Runs as a long-lived subprocess — loads sentence-transformers once,
then processes embed requests via stdin/stdout JSON lines.

Usage: python3 embedder.py [--model sentence-transformers/all-mpnet-base-v2]
"""

import sys
import json
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='sentence-transformers/all-mpnet-base-v2')
    args = parser.parse_args()

    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(args.model)
        dim = model.get_sentence_embedding_dimension()
        sys.stderr.write(f'[embedder] loaded {args.model} dim={dim}\n')
        sys.stderr.flush()
    except ImportError:
        # Fallback: return zero vectors if sentence-transformers not installed
        sys.stderr.write('[embedder] sentence-transformers not available, using zero vectors\n')
        sys.stderr.flush()
        dim = 768
        model = None

    # Signal ready
    sys.stdout.write(json.dumps({'status': 'ready', 'dim': dim}) + '\n')
    sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            texts = req.get('texts', [])
            if model is not None:
                vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
                sys.stdout.write(json.dumps({'vectors': vecs.tolist()}) + '\n')
            else:
                sys.stdout.write(json.dumps({'vectors': [[0.0] * dim for _ in texts]}) + '\n')
            sys.stdout.flush()
        except Exception as e:
            sys.stdout.write(json.dumps({'error': str(e)}) + '\n')
            sys.stdout.flush()


if __name__ == '__main__':
    main()
