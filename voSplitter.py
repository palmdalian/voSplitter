import wave
import audioop
import sys
import subprocess
import math
import os
import csv
import subprocess


# Adjustment parameters
head_adjust = 0.10
tail_adjust = 0.3
db_threshold = -20
min_silence_length = 0.7
min_sound_length = 0.2
sample_number = 100 #The bigger the number, the faster it goes (but loses accuracy)

class SoundFinder():
	def __init__(self, input_path):
		self.input_path = input_path
		root = os.path.dirname(self.input_path)
		base = os.path.basename(self.input_path)
		self.split = os.path.splitext(base)
		self.output = os.path.join(root, "out")
		self.output_base = os.path.join(self.output, self.split[0])
		self.silence_list = []
		self.sound_list = []
		self.convertAudio = False
		self.output_type = "split"
		self.prepare_wav()

	def prepare_wav(self):
		try:
			self.wav = wave.open(self.input_path)
			params = self.wav.getparams()
			# (nchannels, sampwidth, framerate, nframes, comptype, compname)
			if params[0] > 1 or params[1] not in [1,2,4]:
				self.convertAudio = True
		except:
			self.convertAudio = True

		# Create temp pcm file just in case it's not in the right format (24 bit pcm doesn't work here)
		if self.convertAudio is True:
			print("Converting file to 16 bit, mono wave")
			self.converted_path = self.output + "_temp.wav"
			args = ["ffmpeg", "-y", "-v", "quiet", "-i", self.input_path, "-vn", "-ac", "1", "-c:a", "pcm_s16le", self.converted_path]
			subprocess.check_call(args)
			self.wav = wave.open(self.converted_path)


	def find_sound(self):
		self.framerate = self.wav.getframerate()
		sample_width = self.wav.getsampwidth()
		sample_length = float(sample_number) / self.framerate

		db = math.exp(math.log(10.0)*0.05 * db_threshold) # Convert from db to float. Was having trouble with the normal 10**(db/20)
		all_frames = self.wav.readframes(self.wav.getnframes())
		max_amp = audioop.max(all_frames, sample_width)
		self.threshold = db * max_amp
		self.wav.rewind()

		frames = self.wav.readframes(sample_number)
		total_length = 0
		silence_start = -1
		silence_counter = 0
		sound_start = 0
		found_sound = False
		sound_counter = 0

		while (frames):
			amplitute = audioop.rms(frames, sample_width)
			# Is it silence?
			if amplitute < self.threshold:
				if silence_start < 0:
					silence_start = total_length
				if silence_counter > min_silence_length and found_sound and sound_counter > min_sound_length:
					found_sound = False
					sound_counter = 0
					self.sound_list.append([sound_start, total_length])
				silence_counter += sample_length
				
			# No, so we start a
			else:
				if found_sound is False:
					found_sound = True
					silence_counter = 0
					sound_start = total_length
				if silence_counter > 0 and sound_counter > min_sound_length:
					silence_start = -1
					silence_counter = 0
				sound_counter += sample_length

			frames = self.wav.readframes(sample_number)
			total_length += sample_length

		# print("Sound Start: {}, Sound Counter: {}, Silence Counter: {}, Silence Start: {}, FoundSound: {}".format(sound_start, sound_counter, silence_counter, silence_start, found_sound))
		if found_sound and sound_counter > min_sound_length and silence_start > sound_start:
			self.sound_list.append([sound_start, silence_start])
		
		for timing in self.sound_list:
			timing[0] -= head_adjust
			timing[1] += tail_adjust

		# Do a pass to make sure there isn't an overlap. (Sometimes happens with long tails)
		for i in xrange(len(self.sound_list)-1, 0, -1):
			if i-1 >= 0:
				if self.sound_list[i-1][1] - self.sound_list[i][0] > 0.1:
					self.sound_list[i-1][1] = self.sound_list[i][1]
					self.sound_list.pop(i)

	def save_chunks(self):
		if not len(self.sound_list):
			return
		if self.output_type == "trim":
			self.sound_list = [[self.sound_list[0][0], self.sound_list[-1][1]]]
		if not os.path.exists(self.output):
			os.mkdir(self.output)
		for i, sound in enumerate(self.sound_list):
			start_sample = int(math.floor(sound[0] * self.framerate))
			end_sample = int(math.ceil(sound[1] * self.framerate))
			self.wav.rewind()
			self.wav.readframes(start_sample) # Go to the start point
			frames = self.wav.readframes(end_sample-start_sample)

			outpath = "{output_base}_{num}.wav".format(output_base=self.output_base, num=str(i).zfill(3))
			wavout = wave.open(outpath, 'wb')
			wavout.setparams(self.wav.getparams())
			wavout.writeframes(frames)
			wavout.close()
		self.wav.close()
		if self.convertAudio is True:
			os.remove(self.converted_path)

	def save_chunks_ffmpeg(self):
		if not len(self.sound_list):
			return
		if self.output_type == "trim":
			self.sound_list = [[self.sound_list[0][0], self.sound_list[-1][1]]]
		if not os.path.exists(self.output):
			os.mkdir(self.output)
		for i, sound in enumerate(self.sound_list):
			start = sound[0]
			if start < 0.00001: # Weird edge case with pre-edited clips
				start = 0
			end = sound[1]
			outpath = "{output_base}_{num}{ext}".format(output_base=self.output_base, num=str(i).zfill(3), ext=self.split[1])
			args = ['ffmpeg', '-y', '-v', 'quiet', '-i', self.input_path, '-ss', str(start), '-to', str(end), '-c:a', 'copy', outpath]
			subprocess.check_call(args)
		self.wav.close()
		if self.convertAudio is True:
			os.remove(self.converted_path)

if __name__ == '__main__':
	accepted_files = ['.aiff', '.wav', '.mp3', '.aif']
	input_paths = []
	input_path = sys.argv[1]

	if not os.path.isdir(input_path):
		base = os.path.basename(input_path)
		split = os.path.splitext(base)
		if split[-1] in accepted_files:
			input_paths.append(input_path)
	else:
		input_paths = [os.path.join(input_path, x) for x in os.listdir(input_path) if not x.startswith('.') and os.path.splitext(x)[-1] in accepted_files]

	for path in input_paths:
		print path
		finder = SoundFinder(path)
		finder.find_sound()
		print (finder.sound_list)
		finder.output_type = "trim"
		finder.save_chunks_ffmpeg()
