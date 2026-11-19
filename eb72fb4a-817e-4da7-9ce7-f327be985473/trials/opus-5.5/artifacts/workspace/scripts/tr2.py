import json,sys,wave
from vosk import KaldiRecognizer, Model, SetLogLevel
SetLogLevel(-1)
model=Model("/opt/dictation/model")
words="zero oh one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty a b c d e f g h i j k l m n o p q r s t u v w x y z site manager bleep log monday tuesday wednesday thursday friday saturday sunday october staff number started as rostered nothing further note ends called in from on call at home transferring westbrook general starting correction the ward shift reference for check i will keep my phone on attention please would duty porter attend emergency department visiting time medical wards is now ending thank you served on site no handed over reported transfer arrived minutes hours late early at clocked [unk]".split()
for path in sys.argv[1:]:
    with wave.open(path,"rb") as fh:
        rec=KaldiRecognizer(model,fh.getframerate(),json.dumps(words))
        while True:
            d=fh.readframes(4000)
            if not d: break
            rec.AcceptWaveform(d)
        print(path, json.loads(rec.FinalResult()).get('text',''))
