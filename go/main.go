package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io/ioutil"
	"log"
	"math"
	"os"
	"path/filepath"
	"time"

	"github.com/faiface/beep/wav"
	premiere "github.com/palmdalian/premiere_xml"
	"github.com/palmdalian/premiere_xml/builder"
)

func main() {
	var path string
	var jsonOutput bool
	var outputPath string
	var threshold float64
	var samples int
	var minSilence float64
	var minSound float64
	var headAdjust float64
	var tailAdjust float64

	flag.StringVar(&path, "i", "test.wav", "input")
	flag.StringVar(&outputPath, "o", "/tmp/test.xml", "output")
	flag.BoolVar(&jsonOutput, "j", false, "json")
	flag.Float64Var(&threshold, "threshold", -15, "Threshold in db")
	flag.IntVar(&samples, "samples", 800, "Number of samples")
	flag.Float64Var(&minSilence, "silence", 0.9, "Minimum silence length")
	flag.Float64Var(&minSound, "sound", 0.5, "Minimum sound length")
	flag.Float64Var(&headAdjust, "head", 0.2, "Head adjustment")
	flag.Float64Var(&tailAdjust, "tail", 0.7, "Tail adjustment")

	flag.Parse()

	path, err := filepath.Abs(path)

	if err != nil {
		log.Fatal(err)
	}

	detector := &Detector{
		DBThreshold:          threshold,
		SampleNumber:         samples,
		MinimumSilenceLength: minSilence,
		MinimumSoundLength:   minSound,
		HeadAdjust:           headAdjust,
		TailAdjust:           tailAdjust,
	}

	soundList, sampleRate := detector.FindSound(path)
	timings := builderTimings(soundList, sampleRate, path)
	if jsonOutput {
		file, err := json.MarshalIndent(timings, "", " ")
		if err != nil {
			log.Fatal(err)
		}
		err = ioutil.WriteFile(outputPath, file, 0644)
		if err != nil {
			log.Fatal(err)
		}
		return
	}

	pBuilder, err := builder.NewPremiereBuilder()
	if err != nil {
		log.Fatal(err)
	}
	pBuilder.ProcessAudioTimings(timings)
	pBuilder.SaveToPath(outputPath)
}

type SoundTiming struct {
	start float64
	end   float64
}

func (t *SoundTiming) Length() float64 {
	return t.end - t.start
}

type Detector struct {
	DBThreshold          float64
	SampleNumber         int
	MinimumSilenceLength float64
	MinimumSoundLength   float64
	HeadAdjust           float64
	TailAdjust           float64
}

func (d *Detector) FindSound(path string) ([]*SoundTiming, int) {

	f, err := os.Open(path)
	if err != nil {
		log.Fatal(err)
	}
	streamer, format, err := wav.Decode(f)
	if err != nil {
		log.Fatal(err)
	}
	defer streamer.Close()

	sampleRate := format.SampleRate.N(time.Second)
	totalSamples := streamer.Len()
	currentTime := 0.0

	silenceList := []*SoundTiming{}
	silenceStart := -1.0
	for s := 0; s < totalSamples; s += d.SampleNumber {
		samples := make([][2]float64, d.SampleNumber)
		n, ok := streamer.Stream(samples)
		if !ok {
			continue
		}
		if n < d.SampleNumber {
			samples = samples[:n]
		}

		currentTime = float64(s) / float64(sampleRate)

		amplitude := peak(samples)

		if d.DBThreshold > amplitude && silenceStart < 0 { // Sample is silence
			silenceStart = currentTime
		} else if amplitude > d.DBThreshold && silenceStart >= 0 { // Sample is sound
			timing := &SoundTiming{start: silenceStart, end: currentTime}
			if timing.Length() > d.MinimumSilenceLength {
				silenceList = append(silenceList, timing)
			}
			silenceStart = -1
		}
	}
	if silenceStart > 0 {
		timing := &SoundTiming{start: silenceStart, end: currentTime}
		if timing.Length() > d.MinimumSilenceLength {
			silenceList = append(silenceList, timing)
		}
	}

	sounds := []*SoundTiming{
		&SoundTiming{start: 0, end: 0},
	}
	for _, s := range silenceList {
		last := sounds[len(sounds)-1]
		last.end = s.start + d.TailAdjust
		sounds = append(sounds, &SoundTiming{start: s.end - d.HeadAdjust, end: 0})
	}
	lastSound := sounds[len(sounds)-1]
	if lastSound.start == currentTime {
		sounds = sounds[:len(sounds)-1]
	} else {
		lastSound.end = currentTime + d.TailAdjust
	}

	filteredSounds := []*SoundTiming{}
	for _, s := range sounds {
		// Combine timings if necessary
		if len(filteredSounds) > 0 {
			last := filteredSounds[len(filteredSounds)-1]
			if last.end > s.start {
				last.end = s.end
				continue
			}
		}

		if s.Length() > d.MinimumSoundLength {
			filteredSounds = append(filteredSounds, s)
		}
	}
	return filteredSounds, sampleRate
}

func peak(samples [][2]float64) float64 {
	min := 0.0
	max := 0.0
	for _, s := range samples {
		sample := s[0] // Only do the first channel
		if sample > max {
			max = sample
		} else if sample < min {
			min = sample
		}
	}
	if max > math.Abs(min) {
		return 20 * math.Log10(max)
	}

	return 20 * math.Log10(math.Abs(min))
}

func builderTimings(soundTimings []*SoundTiming, sampleRate int, path string) []*builder.Timing {
	timings := []*builder.Timing{}
	for _, t := range soundTimings {
		timing := &builder.Timing{
			Start:     int64(t.start * float64(sampleRate)),
			End:       int64(t.end * float64(sampleRate)),
			Rate:      int64(sampleRate),
			StartTick: fmt.Sprintf("%d", int64(float64(t.start)*premiere.PProTicksConstant)),
			EndTick:   fmt.Sprintf("%d", int64(float64(t.end)*premiere.PProTicksConstant)),
			Path:      path,
		}
		timings = append(timings, timing)
	}
	return timings
}
