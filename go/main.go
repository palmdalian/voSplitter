package main

import (
	"flag"
	"fmt"
	"log"
	"math"
	"os"
	"path/filepath"
	"time"

	"github.com/faiface/beep/wav"
)

func main() {
	var path string
	flag.StringVar(&path, "f", "test.wav", "filepath")
	flag.Parse()

	path, err := filepath.Abs(path)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println(path)

	detector := &Detector{
		DBThreshold:          -15.0,
		SampleNumber:         800,
		MinimumSilenceLength: 0.9,
		MinimumSoundLength:   0.5,
		HeadAdjust:           0.2,
		TailAdjust:           0.7,
	}

	list := detector.FindSound(path)
	for _, s := range list {
		fmt.Println("PEAK", s)
	}
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

func (d *Detector) FindSound(path string) []*SoundTiming {

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
		last.end = s.start
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
	return filteredSounds
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
