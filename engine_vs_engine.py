import time, chess, chess.engine

ENGINE_PATHS = {"Engine A": "", "Engine B": ""}

def start_engine(path): return chess.engine.SimpleEngine.popen_uci(path)

def configure_engine(e, opts):
    if not opts: return
    try: e.configure(opts)
    except: pass

def get_move(engine, board, w_ms, b_ms):
    start = time.monotonic()
    limit = chess.engine.Limit(time=max(0.001, (w_ms/1000.0 if board.turn == chess.WHITE else b_ms/1000.0)))
    try:
        res = engine.play(board, limit, info=chess.engine.INFO_ALL)
    except:
        return None, None, None, None, None, 0.0
    elapsed = (time.monotonic() - start) * 1000.0
    mv = res.move.uci() if res.move else None
    info = res.info
    depth = info.get("depth"); nodes = info.get("nodes")
    nps = nodes / (elapsed/1000.0) if nodes and elapsed>0 else None
    score_cp = score_mate = None
    score = info.get("score")
    if score is not None:
        try:
            pov = score.white() if board.turn==chess.WHITE else score.black()
            score_mate = pov.mate() if pov.is_mate() else None
            score_cp = None if pov.is_mate() else pov.score()
        except: pass
    return mv, depth, nodes, nps, score_cp, score_mate, elapsed

def run_match(n1,p1,n2,p2,conf):
    print(f"START: {n1} vs {n2}")
    e1 = e2 = None
    board = chess.Board(conf.get('initial_fen') or chess.STARTING_FEN)
    t1 = t2 = conf.get('timelimit_ms',9000)
    result = "*"
    try:
        e1 = start_engine(p1); e2 = start_engine(p2)
        opts = {"Hash": conf.get("hash_size"), "Threads": conf.get("threads")}
        configure_engine(e1, opts); configure_engine(e2, opts)
        pgn = ""; moves=0
        while not board.is_game_over(claim_draw=True) and moves < conf.get('num_moves',1000):
            white = board.turn==chess.WHITE
            engine = e1 if white else e2
            mv, depth, nodes, nps, scp, smate, elapsed = get_move(engine, board, t1, t2)
            if white:
                t1 = t1 - elapsed + conf.get('increment_ms',0)
            else:
                t2 = t2 - elapsed + conf.get('increment_ms',0)
            if not mv:
                result = "0-1" if white else "1-0"; break
            move = chess.Move.from_uci(mv)
            if move not in board.legal_moves:
                result = "0-1" if white else "1-0"; break
            san = board.san(move); board.push(move)
            if white: pgn += f"{board.fullmove_number}. {san} "
            else: pgn += f"{san} "
            moves += 1
        else:
            result = board.result(claim_draw=True)
        print("END:", result)
        print("PGN:\n", pgn.strip())
    except:
        print("ERRO. Partida interrompida.")
    finally:
        for e in (e1,e2):
            if e:
                try: e.quit()
                except: pass

if __name__=="__main__":
    cfg = {'hash_size':2000,'threads':1,'timelimit_ms':100,'increment_ms':0,'num_moves':1000,'initial_fen':"rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"}
    run_match("Engine A", ENGINE_PATHS["Engine A"], "Engine B", ENGINE_PATHS["Engine B"], cfg)
