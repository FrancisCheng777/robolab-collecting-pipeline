"""Offline native H5 review and non-destructive selection editor."""
import argparse
from pathlib import Path

from .core import Config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', default='data/raw', help='Recursively scan completed H5 files')
    parser.add_argument('--output', default='outputs/review/selected', help='Selected native H5 output')
    parser.add_argument('--clips', default='outputs/review/clips.json')
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--speed', type=float, default=1.)
    args = parser.parse_args()
    if not .25 <= args.speed <= 4:
        parser.error('--speed must be between 0.25 and 4')
    import uvicorn
    from .server import create_app
    config = Config(input_dir=str(Path(args.input).absolute()),
                    output=str(Path(args.output).absolute()))
    app = create_app(config, Path(args.clips).absolute())

    @app.get('/api/player')
    def player():
        return {'speed': args.speed}

    print(f'Review: http://127.0.0.1:{args.port}\nInput: {config.input_dir}\n'
          f'Plan: {args.clips}\nSelected H5: {config.output}', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
