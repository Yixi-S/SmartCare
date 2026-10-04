-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1
-- Generation Time: Oct 04, 2026 at 01:41 PM
-- Server version: 10.4.32-MariaDB
-- PHP Version: 8.2.12

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `smartcare`
--

-- --------------------------------------------------------

--
-- Table structure for table `appointments`
--

CREATE TABLE `appointments` (
  `appointment_id` int(11) NOT NULL,
  `patient_id` int(11) NOT NULL,
  `practitioner_id` int(11) NOT NULL,
  `appt_date` date NOT NULL,
  `appt_time` time NOT NULL,
  `status` enum('Scheduled','Completed','Cancelled','No-Show') NOT NULL DEFAULT 'Scheduled',
  `reason` varchar(200) DEFAULT NULL,
  `cancellation_reason` varchar(200) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `active_slot` tinyint(4) GENERATED ALWAYS AS (if(`status` = 'Cancelled',NULL,1)) STORED
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Table structure for table `appointment_history`
--

CREATE TABLE `appointment_history` (
  `history_id` int(11) NOT NULL,
  `appointment_id` int(11) NOT NULL,
  `action` varchar(30) NOT NULL,
  `old_status` varchar(20) DEFAULT NULL,
  `new_status` varchar(20) DEFAULT NULL,
  `old_datetime` datetime DEFAULT NULL,
  `new_datetime` datetime DEFAULT NULL,
  `notes` varchar(255) DEFAULT NULL,
  `changed_by` varchar(60) DEFAULT NULL,
  `changed_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Table structure for table `patients`
--

CREATE TABLE `patients` (
  `patient_id` int(11) NOT NULL,
  `first_name` varchar(60) NOT NULL,
  `last_name` varchar(60) NOT NULL,
  `dob` date NOT NULL,
  `phone` varchar(20) NOT NULL,
  `email` varchar(120) DEFAULT NULL,
  `address` varchar(200) DEFAULT NULL,
  `notes` varchar(500) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `patients`
--

INSERT INTO `patients` (`patient_id`, `first_name`, `last_name`, `dob`, `phone`, `email`, `address`, `notes`, `created_at`, `updated_at`) VALUES
(1, 'Olivia', 'Brown', '1988-04-12', '0400111222', 'OliB@Gmail.com', '12 Park St, Sydney', NULL, '2026-10-01 12:37:25', '2026-10-01 12:39:37'),
(2, 'Liam', 'Wilson', '1975-09-30', '0400333444', 'Sonion@Hotmail.com', '11 Chud Lane Brisbane', NULL, '2026-10-01 12:37:25', '2026-10-01 12:40:37'),
(3, 'Sophie', 'Taylor', '2001-01-22', '0400555666', 'TaylorSwiftSop@Gmail.com', 'Okami Braddon Canberra', NULL, '2026-10-01 12:37:25', '2026-10-01 12:40:21');

-- --------------------------------------------------------

--
-- Table structure for table `practitioners`
--

CREATE TABLE `practitioners` (
  `practitioner_id` int(11) NOT NULL,
  `full_name` varchar(100) NOT NULL,
  `specialty` varchar(80) NOT NULL DEFAULT 'General Practice',
  `phone` varchar(20) DEFAULT NULL,
  `email` varchar(120) DEFAULT NULL,
  `active` tinyint(1) NOT NULL DEFAULT 1,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `practitioners`
--

INSERT INTO `practitioners` (`practitioner_id`, `full_name`, `specialty`, `phone`, `email`, `active`, `created_at`) VALUES
(1, 'Dr Isla Frost', 'General Practice', '0291110001', 'i.Frost@Gmail.com', 1, '2026-10-01 12:37:25'),
(2, 'Dr Ravi Patel', 'General Practice', '0291110002', 'R.Patel@gmail.com', 1, '2026-10-01 12:37:25'),
(3, 'Dr Samson Smalls', 'General Practice', '0291110003', 'S.Smalls@Hotmail.com', 1, '2026-10-01 12:37:25');

-- --------------------------------------------------------

--
-- Table structure for table `practitioner_availability`
--

CREATE TABLE `practitioner_availability` (
  `availability_id` int(11) NOT NULL,
  `practitioner_id` int(11) NOT NULL,
  `day_of_week` tinyint(4) NOT NULL,
  `start_time` time NOT NULL,
  `end_time` time NOT NULL
) ;

--
-- Dumping data for table `practitioner_availability`
--

INSERT INTO `practitioner_availability` (`availability_id`, `practitioner_id`, `day_of_week`, `start_time`, `end_time`) VALUES
(1, 1, 0, '09:00:00', '13:00:00'),
(2, 1, 2, '09:00:00', '13:00:00'),
(3, 1, 4, '09:00:00', '12:00:00'),
(4, 2, 1, '10:00:00', '16:00:00'),
(5, 2, 3, '10:00:00', '16:00:00'),
(6, 3, 0, '13:00:00', '17:00:00'),
(7, 3, 2, '13:00:00', '17:00:00'),
(8, 3, 4, '13:00:00', '17:00:00');

-- --------------------------------------------------------

--
-- Table structure for table `staff_accounts`
--

CREATE TABLE `staff_accounts` (
  `staff_id` int(11) NOT NULL,
  `username` varchar(40) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `full_name` varchar(100) NOT NULL,
  `active` tinyint(1) NOT NULL DEFAULT 1,
  `failed_attempts` int(11) NOT NULL DEFAULT 0,
  `locked_until` datetime DEFAULT NULL,
  `last_login` datetime DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `staff_accounts`
--

INSERT INTO `staff_accounts` (`staff_id`, `username`, `password_hash`, `full_name`, `active`, `failed_attempts`, `locked_until`, `last_login`, `created_at`) VALUES
(1, 'admin', 'pbkdf2_sha256$200000$58722d2d433ac59891033dc94c449ee6$7edb157a285c296c24c9b2a2b4f35b0a3760895a4928cc843edd027e4cd698ad', 'Clinic Administrator', 1, 0, NULL, NULL, '2026-10-01 12:37:25'),
(2, 'reception', 'pbkdf2_sha256$200000$fe9bfb305e812f6f925a72fd2821d9b3$e8367bea71df423e7f7a51b894670eedf3613dca8d410ca89922e5e7fe93f565', 'Front Desk', 1, 0, NULL, NULL, '2026-10-01 12:37:25');

--
-- Indexes for dumped tables
--

--
-- Indexes for table `appointments`
--
ALTER TABLE `appointments`
  ADD PRIMARY KEY (`appointment_id`),
  ADD UNIQUE KEY `uq_prac_slot` (`practitioner_id`,`appt_date`,`appt_time`,`active_slot`),
  ADD UNIQUE KEY `uq_patient_slot` (`patient_id`,`appt_date`,`appt_time`,`active_slot`),
  ADD KEY `idx_appt_date` (`appt_date`);

--
-- Indexes for table `appointment_history`
--
ALTER TABLE `appointment_history`
  ADD PRIMARY KEY (`history_id`),
  ADD KEY `fk_hist_appt` (`appointment_id`);

--
-- Indexes for table `patients`
--
ALTER TABLE `patients`
  ADD PRIMARY KEY (`patient_id`),
  ADD UNIQUE KEY `uq_patient_identity` (`first_name`,`last_name`,`dob`),
  ADD KEY `idx_patient_name` (`last_name`,`first_name`),
  ADD KEY `idx_patient_phone` (`phone`);

--
-- Indexes for table `practitioners`
--
ALTER TABLE `practitioners`
  ADD PRIMARY KEY (`practitioner_id`);

--
-- Indexes for table `practitioner_availability`
--
ALTER TABLE `practitioner_availability`
  ADD PRIMARY KEY (`availability_id`),
  ADD KEY `fk_avail_prac` (`practitioner_id`);

--
-- Indexes for table `staff_accounts`
--
ALTER TABLE `staff_accounts`
  ADD PRIMARY KEY (`staff_id`),
  ADD UNIQUE KEY `username` (`username`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `appointments`
--
ALTER TABLE `appointments`
  MODIFY `appointment_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `appointment_history`
--
ALTER TABLE `appointment_history`
  MODIFY `history_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `patients`
--
ALTER TABLE `patients`
  MODIFY `patient_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=4;

--
-- AUTO_INCREMENT for table `practitioners`
--
ALTER TABLE `practitioners`
  MODIFY `practitioner_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=4;

--
-- AUTO_INCREMENT for table `practitioner_availability`
--
ALTER TABLE `practitioner_availability`
  MODIFY `availability_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `staff_accounts`
--
ALTER TABLE `staff_accounts`
  MODIFY `staff_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=3;

--
-- Constraints for dumped tables
--

--
-- Constraints for table `appointments`
--
ALTER TABLE `appointments`
  ADD CONSTRAINT `fk_appt_patient` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`patient_id`),
  ADD CONSTRAINT `fk_appt_prac` FOREIGN KEY (`practitioner_id`) REFERENCES `practitioners` (`practitioner_id`);

--
-- Constraints for table `appointment_history`
--
ALTER TABLE `appointment_history`
  ADD CONSTRAINT `fk_hist_appt` FOREIGN KEY (`appointment_id`) REFERENCES `appointments` (`appointment_id`) ON DELETE CASCADE;

--
-- Constraints for table `practitioner_availability`
--
ALTER TABLE `practitioner_availability`
  ADD CONSTRAINT `fk_avail_prac` FOREIGN KEY (`practitioner_id`) REFERENCES `practitioners` (`practitioner_id`) ON DELETE CASCADE;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
